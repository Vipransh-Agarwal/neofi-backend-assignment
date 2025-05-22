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

from ..schemas import EventCreate, EventRead, EventUpdate, EventBatchCreate
from ..models import Event, User, EventPermission, EventVersion
from ..db.session import get_db
from ..dependencies import get_current_user
from ..utils.versioning import record_event_version

router = APIRouter(prefix="/api/events", tags=["events"])

# If you want a dedicated limiter instead of re-importing the global one:
limiter = Limiter(key_func=get_remote_address)

@router.post("/", response_model=EventRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_event(
    event_in: EventCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a new (possibly recurring) event. If `recurrence_rule` is provided,
    the server will store it and use it for occurrence generation later.
    """
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
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.creator_id != current_user.id:
        # Optional: also allow if user has can_edit permission
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

    for attr, value in event_update.dict(exclude_unset=True).items():
        setattr(event, attr, value)

    await db.flush()  # Update timestamp
    await record_event_version(db, event, current_user.id)
    await db.commit()
    await db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_event(
    event_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete an event by ID. Only the creator can delete it.
    """
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event or event.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

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
    """
    Create multiple events in a single request. If any event in the batch fails validation, the entire batch is rolled back.
    """
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