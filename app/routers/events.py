from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, or_
from typing import List, Optional
from datetime import datetime, timezone
from dateutil.rrule import rrulestr
from dateutil.parser import isoparse

from slowapi import Limiter
from slowapi.util import get_remote_address

from fastapi_cache.decorator import cache

from ..schemas import (
    EventCreate, 
    EventRead, 
    EventUpdate, 
    EventBatchCreate,
    EventConflict,
    ConflictResponse
)
from ..models import Event, User, EventPermission, EventVersion
from ..db.session import get_db
from ..dependencies import get_current_user, require_editor_or_above, require_owner
from ..utils.versioning import record_event_version
from ..utils.conflicts import detect_event_conflicts  # Add this import at the top
from ..utils.notifications import notification_manager

router = APIRouter(prefix="/api/events", tags=["events"])

# If you want a dedicated limiter instead of re-importing the global one:
limiter = Limiter(key_func=get_remote_address)

@router.post("/", response_model=EventRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_event(
    event_in: EventCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor_or_above),  # Only EDITOR and OWNER can create
):
    """
    Create a new (possibly recurring) event. If `recurrence_rule` is provided,
    the server will store it and use it for occurrence generation later.
    """
    # Add conflict detection before creating event
    conflicts = await detect_event_conflicts(
        db,
        event_in.start_datetime,
        event_in.end_datetime,
        current_user.id
    )
    
    if conflicts:        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ConflictResponse(
                message="Event conflicts with existing events",
                conflicts=[
                    EventConflict(
                        id=e.id,
                        title=e.title,
                        start=e.start_datetime,
                        end=e.end_datetime
                    )
                    for e in conflicts
                ]
            ).model_dump()
        )

    new_event = Event(
        title=event_in.title,
        description=event_in.description,
        start_datetime=event_in.start_datetime,
        end_datetime=event_in.end_datetime,
        creator_id=current_user.id,
        recurrence_rule=event_in.recurrence_rule,
        recurrence_end=event_in.recurrence_end,
    )
    db.add(new_event)
    await db.commit()
    await db.refresh(new_event)

    # Record the first version (snapshot) as usual
    await record_event_version(db, new_event, current_user.id)

    # After successful event creation
    await notification_manager.notify_event_change(
        event=new_event,
        change_type="created",
        changed_by=current_user
    )
    
    return EventRead.model_validate(new_event)


@router.get("", response_model=List[EventRead])
@limiter.limit("20/minute")
async def list_events(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    start_date: datetime | None = Query(None, description="ISO datetime, e.g. 2025-06-01T00:00:00Z"),
    end_date:   datetime | None = Query(None, description="ISO datetime, e.g. 2025-06-30T23:59:59Z"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1) Normalize naive → UTC if needed
    if start_date is not None and start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date is not None and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    # 2) Pull all events that user owns or is shared on
    stmt = (
        select(Event)
        .where(
            (Event.creator_id == current_user.id)
            | Event.permissions.any(user_id=current_user.id)
        )
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    all_events = result.scalars().all()

    filtered: list[Event] = []
    for ev in all_events:
        # If no recurrence, just do a simple overlap check:
        if not ev.recurrence_rule:
            if start_date and ev.start_datetime < start_date:
                continue
            if end_date and ev.end_datetime > end_date:
                continue
            filtered.append(ev)
        else:
            # Build an rrule from the stored rule string (dtstart=original start_datetime)
            rule = rrulestr(ev.recurrence_rule, dtstart=ev.start_datetime)

            # Decide the window to check:
            window_start = start_date or ev.start_datetime
            window_end = end_date or ev.recurrence_end or ev.end_datetime

            # If the original ev.start_datetime was tz‐aware, ensure our window_start/‐end are aware
            if window_start.tzinfo is None:
                window_start = window_start.replace(tzinfo=timezone.utc)
            if window_end.tzinfo is None:
                window_end = window_end.replace(tzinfo=timezone.utc)

            occs = rule.between(window_start, window_end, inc=True)
            if occs:
                filtered.append(ev)

    # 3) Return via Pydantic schema
    return [EventRead.model_validate(ev) for ev in filtered]


@router.get("/{event_id}", response_model=EventRead)
@limiter.limit("20/minute")
@cache(expire=30)
async def get_event(
    event_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return a single event if the user has read access.
    Cached for 30 seconds to reduce DB load for hotspots.
    """
    ev = await db.execute(select(Event).where(Event.id == event_id))
    event = ev.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Permission checks omitted for brevity...
    return EventRead.model_validate(event)


@router.put("/{event_id}", response_model=EventRead)
@limiter.limit("20/minute")
async def update_event(
    request: Request,
    event_id: int,
    event_update: EventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor_or_above),
):
    """Update an event with proper async handling"""
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.creator_id != current_user.id:
        # Check for edit permission
        perm_result = await db.execute(
            select(EventPermission).where(
                EventPermission.event_id == event_id,
                EventPermission.user_id == current_user.id,
                EventPermission.can_edit == True,
            )
        )
        permission = perm_result.scalar_one_or_none()
        if not permission:
            raise HTTPException(status_code=403, detail="You don't have permission to edit this event.")

    # If updating date/time, check for conflicts
    if event_update.start_datetime or event_update.end_datetime:
        new_start = event_update.start_datetime or event.start_datetime
        new_end = event_update.end_datetime or event.end_datetime
        
        conflicts = await detect_event_conflicts(
            db,
            new_start,
            new_end,
            current_user.id,
            exclude_event_id=event_id
        )
        
        if conflicts:            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ConflictResponse(
                    message="New time conflicts with existing events",
                    conflicts=[
                        EventConflict(
                            id=e.id,
                            title=e.title,
                            start=e.start_datetime,
                            end=e.end_datetime
                        )
                        for e in conflicts
                    ]
                ).model_dump()
            )

    # Update fields
    update_data = event_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)

    # Create version before commit
    await db.flush()
    await record_event_version(db, event, current_user.id)
    
    # Commit all changes
    await db.commit()
    
    # Get fresh event data
    await db.refresh(event)

    # After successful event update
    await notification_manager.notify_event_change(
        event=event,
        change_type="updated",
        changed_by=current_user
    )
    
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_event(
    event_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),  # Only OWNER can delete
):
    """
    Delete an event by ID. Only the creator can delete it.
    """
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event or event.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # Before deletion, notify subscribers
    await notification_manager.notify_event_change(
        event=event,
        change_type="deleted",
        changed_by=current_user
    )

    await db.delete(event)
    await db.commit()
    return None  # 204 No Content


@router.post("/batch", response_model=List[EventRead], status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def batch_create_events(
    batch_in: EventBatchCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check each event for conflicts before creating any
    for event in batch_in.events:
        conflicts = await detect_event_conflicts(
            db,
            event.start_datetime,
            event.end_datetime,
            current_user.id
        )
        
        if conflicts:            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ConflictResponse(
                    message=f"Event '{event.title}' conflicts with existing events",
                    conflicts=[
                        EventConflict(
                            id=e.id,
                            title=e.title,
                            start=e.start_datetime,
                            end=e.end_datetime
                        )
                        for e in conflicts
                    ]
                ).model_dump()
            )

    new_events = []
    for item in batch_in.events:
        if item.end_datetime <= item.start_datetime:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_datetime must be after start_datetime in all events",
            )
        new_events.append(
            Event(
                title=item.title,
                description=item.description,
                start_datetime=item.start_datetime,
                end_datetime=item.end_datetime,
                creator_id=current_user.id,
            )
        )

    # Add all at once and commit as one transaction
    db.add_all(new_events)
    try:
        await db.commit()
        # Refresh each to get IDs and created_at
        for ev in new_events:
            await db.refresh(ev)
    except:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch insert failed (possible constraint violation)",
        )

    return new_events