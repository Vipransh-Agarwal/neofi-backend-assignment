from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from typing import List

from ..schemas import EventCreate, EventRead, EventUpdate, EventBatchCreate
from ..models import Event, User
from ..db.session import get_db
from ..dependencies import get_current_user

router = APIRouter(prefix="/api/events", tags=["events"])

@router.post("/", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    event_in: EventCreate,
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
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not create event (possible constraint violation)",
        )

    return new_event


@router.get("/", response_model=List[EventRead])
async def list_events(
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
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve a single event by its ID—only if the current_user is the creator.
    """
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event or event.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@router.put("/{event_id}", response_model=EventRead)
async def update_event(
    event_id: int,
    event_in: EventUpdate,
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
    await db.commit()
    await db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: int,
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
async def batch_create_events(
    batch_in: EventBatchCreate,
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