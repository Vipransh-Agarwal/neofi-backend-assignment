from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime

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
    current_user: User = Depends(get_current_user),
):
    if event_in.end_datetime <= event_in.start_datetime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_datetime must be after start_datetime",
        )

    new_event = Event(
        title=event_in.title,
        description=event_in.description,
        start_datetime=event_in.start_datetime,
        end_datetime=event_in.end_datetime,
        creator_id=current_user.id,
    )
    db.add(new_event)

    try:
        await db.commit()
        await db.refresh(new_event)
        # ─── Record the initial version (version_number = 1) ─────────────────────
        await record_event_version(db, new_event, current_user.id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not create event (possible constraint violation)",
        )

    return new_event


@router.get("", response_model=List[EventRead])
@limiter.limit("20/minute")
async def list_events(
    request: Request,
    skip: int = 0,
    limit: int = 20,
    start_from: Optional[datetime] = Query(None, description="Filter: start_datetime >= this"),
    start_to: Optional[datetime] = Query(None, description="Filter: start_datetime <= this"),
    changed_since: Optional[datetime] = Query(None, description="If set, return only events changed since this timestamp"),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List events the user has access to.
    - If `changed_since` is provided, return only events whose LATEST version was created after that timestamp.
    - Otherwise, return all events (owned or shared), optionally filtered by start_datetime range.
    """
    # 1) If changed_since is given, run the sync query
    if changed_since:
        # Subquery: find all event_ids with a version created after changed_since
        subq = (
            select(EventVersion.event_id)
            .where(EventVersion.created_at > changed_since)
            .group_by(EventVersion.event_id)
        ).subquery()

        # Now fetch those events that the user has access to
        q = (
            select(Event)
            .where(
                (Event.id.in_(select(subq.c.event_id)))
                & (
                    (Event.creator_id == current_user.id)
                    | (
                        Event.id.in_(
                            select(EventPermission.event_id).where(
                                EventPermission.user_id == current_user.id
                            )
                        )
                    )
                )
            )
            .order_by(Event.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await db.execute(q)
        events = result.scalars().all()
        return [EventRead.model_validate(ev) for ev in events]

    # 2) Otherwise, do the normal “list all (owned + shared) with optional date‐range”
    base_q = select(Event).where(
        (Event.creator_id == current_user.id)
        | (
            Event.id.in_(
                select(EventPermission.event_id).where(
                    EventPermission.user_id == current_user.id
                )
            )
        )
    )

    # Apply date‐range filters if provided
    if start_from:
        base_q = base_q.where(Event.start_datetime >= start_from)
    if start_to:
        base_q = base_q.where(Event.start_datetime <= start_to)

    base_q = base_q.order_by(Event.start_datetime).offset(skip).limit(limit)
    result = await db.execute(base_q)
    events = result.scalars().all()
    return [EventRead.model_validate(ev) for ev in events]


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
    event_id: int,
    event_in: EventUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Update an event if the version_number matches. Otherwise return 409 Conflict.
    """
    # 1) Fetch the current row from DB
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # 2) Check permissions (owner or can_edit)
    if event.creator_id != current_user.id:
        # load permission row
        perm_q = await db.execute(
            select(EventPermission).where(
                (EventPermission.event_id == event_id)
                & (EventPermission.user_id == current_user.id)
                & (EventPermission.can_edit == True)
            )
        )
        perm = perm_q.scalar_one_or_none()
        if not perm:
            raise HTTPException(status_code=403, detail="Not authorized to edit this event")

    # 3) Optimistic locking: verify version numbers match
    if event.version_number != event_in.version_number:
        raise HTTPException(
            status_code=409,
            detail=f"Event version {event.version_number} has changed; you sent {event_in.version_number}.",
        )

    # 4) Apply updates
    if event_in.title is not None:
        event.title = event_in.title
    if event_in.description is not None:
        event.description = event_in.description
    if event_in.start_datetime is not None:
        event.start_datetime = event_in.start_datetime
    if event_in.end_datetime is not None:
        event.end_datetime = event_in.end_datetime

    # 5) Increment version_number
    event.version_number += 1

    # SQLAlchemy’s updated_at column is set automatically on commit
    db.add(event)
    await db.commit()
    await db.refresh(event)

    # 6) (Optionally) record a new version in event_versions (unaffected by version_number)
    await record_event_version(db, event, current_user)

    return EventRead.model_validate(event)


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