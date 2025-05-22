from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from typing import List

from slowapi import Limiter
from slowapi.util import get_remote_address

from fastapi_cache.decorator import cache

from ..schemas import EventCreate, EventRead, EventUpdate, EventBatchCreate
from ..models import Event, User, EventPermission
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


@router.get("/", response_model=List[EventRead])
@limiter.limit("20/minute")
async def list_events(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all events owned by the current_user, with simple pagination.
    """
    result = await db.execute(
        select(Event)
        .where(Event.creator_id == current_user.id)
        .offset(skip)
        .limit(limit)
        .order_by(Event.start_datetime)
    )
    events = result.scalars().all()
    return events


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
    current_user: User = Depends(get_current_user),
):
    """
    Update fields on an existing event. Only non‐null fields in EventUpdate will be applied.
    Only the creator can update.
    """
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event or event.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # ─── Authorization: only owner or shared with can_edit=True ─────────────
    if event.creator_id != current_user.id:
        perm_result = await db.execute(
            select(EventPermission).where(
                EventPermission.event_id == event_id,
                EventPermission.user_id == current_user.id,
            )
        )
        perm = perm_result.scalar_one_or_none()
        if not perm or not perm.can_edit:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    
    # Apply updates if provided
    if event_in.start_datetime is not None:
        event.start_datetime = event_in.start_datetime
    if event_in.end_datetime is not None:
        event.end_datetime = event_in.end_datetime
    if event_in.title is not None:
        event.title = event_in.title
    if event_in.description is not None:
        event.description = event_in.description

    # Validate that end > start (if both were updated)
    if event.end_datetime <= event.start_datetime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_datetime must be after start_datetime",
        )

    db.add(event)
    await db.flush()
    
    # ─── Record a new version/diffs ────────────────────────────────────────
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