from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, or_
from typing import List, Optional
from datetime import datetime
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
    skip: int = 0,
    limit: int = 20,
    start_from: Optional[datetime] = Query(
        None, description="Include occurrences with start_datetime >= this"
    ),
    start_to: Optional[datetime] = Query(
        None, description="Include occurrences with start_datetime <= this"
    ),
    changed_since: Optional[datetime] = Query(
        None, description="Return only events changed since this timestamp"
    ),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List events (including expanded recurring occurrences) that the user can access.
    - If `changed_since` is provided, do the “sync” logic, ignoring recurrence expansion.
    - Otherwise, return both one-off events and expanded recurring instances within [start_from, start_to].
    """

    # ─── Sync path (as before) ─────────────────────────────────────────────────────
    if changed_since:
        subq = (
            select(EventVersion.event_id)
            .where(EventVersion.created_at > changed_since)
            .group_by(EventVersion.event_id)
        ).subquery()

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

    # ─── Normal listing with recurrence expansion ─────────────────────────────────
    if start_from is None or start_to is None:
        raise HTTPException(
            status_code=400,
            detail="Both start_from and start_to must be provided when listing events",
        )

    # 1) Fetch all one-off events (recurrence_rule IS NULL) in the given window
    base_q = select(Event).where(
        and_(
            Event.recurrence_rule.is_(None),
            Event.start_datetime >= start_from,
            Event.start_datetime <= start_to,
            or_(
                Event.creator_id == current_user.id,
                Event.id.in_(
                    select(EventPermission.event_id).where(
                        EventPermission.user_id == current_user.id
                    )
                ),
            ),
        )
    )

    # 2) Fetch all “recurring master events” that *could* have occurrences in [start_from, start_to].
    #    i.e. events where recurrence_rule IS NOT NULL, AND:
    #      - `start_datetime` <= start_to (the original start <= window end)
    #      - AND (recurrence_end IS NULL OR recurrence_end >= start_from).
    rec_q = select(Event).where(
        and_(
            Event.recurrence_rule.is_not(None),
            Event.start_datetime <= start_to,
            or_(
                Event.recurrence_end.is_(None),
                Event.recurrence_end >= start_from,
            ),
            or_(
                Event.creator_id == current_user.id,
                Event.id.in_(
                    select(EventPermission.event_id).where(
                        EventPermission.user_id == current_user.id
                    )
                ),
            ),
        )
    )

    one_off_result = await db.execute(base_q)
    one_off_events = one_off_result.scalars().all()

    recurring_result = await db.execute(rec_q)
    recurring_events = recurring_result.scalars().all()

    # 3) For each recurring master event, build its occurrences within [start_from, start_to].
    expanded_occurrences = []
    for ev in recurring_events:
        if not ev.recurrence_rule:
            continue  # sanity check

        # Parse the RRULE string in the context of the event’s DTSTART
        # Example: ev.recurrence_rule = "FREQ=WEEKLY;BYDAY=MO,WE,FR;INTERVAL=1"
        # The dateutil.rrulestr(...) can parse that, but we need to supply dtstart.
        try:
            rule = rrulestr(ev.recurrence_rule, dtstart=ev.start_datetime)
        except Exception as e:
            # If an invalid RRULE was stored, skip expansion
            continue

        # Determine the window to generate occurrences
        # We’ll ask for all occurrences between start_from and start_to (inclusive).
        # But rrulestr by default yields all future occurrences (to a max). To bound it:
        between = rule.between(
            start_from,
            start_to,
            inc=True,  # inclusive
        )

        for occ_start in between:
            # Compute the corresponding end time: assume the duration is (ev.end - ev.start)
            duration = ev.end_datetime - ev.start_datetime
            occ_end = occ_start + duration

            # Build a “virtual” EventRead object that represents this occurrence.
            # We need a unique ID? Often we just leave id = master id, and client treats it as occurrence.
            occurrence = EventRead(
                id=ev.id,
                creator_id=ev.creator_id,
                title=ev.title,
                description=ev.description,
                start_datetime=occ_start,
                end_datetime=occ_end,
                recurrence_rule=ev.recurrence_rule,
                recurrence_end=ev.recurrence_end,
                version_number=ev.version_number,
                updated_at=ev.updated_at,
            )
            expanded_occurrences.append(occurrence)

    # 4) Combine one-offs and expanded occurrences → sort by start_datetime
    combined = one_off_events[:]  # ORM objects
    combined += expanded_occurrences  # Pydantic‐validated models

    # Convert all ORM events to Pydantic first, then combine with occurrence instances
    one_off_read = [EventRead.model_validate(o) for o in one_off_events]
    all_events = one_off_read + expanded_occurrences

    # Sort by start_datetime
    all_events.sort(key=lambda e: e.start_datetime)

    # Apply skip/limit on the combined list (in‐memory)
    sliced = all_events[skip : skip + limit]
    return sliced


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
    Update an event or its recurrence fields. Clients must supply version_number.
    """
    # 1) Fetch and permissions (omitted for brevity)
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # permission check omitted...

    # 2) Optimistic locking
    if event.version_number != event_in.version_number:
        raise HTTPException(
            status_code=409,
            detail=f"Event version {event.version_number} has changed; you sent {event_in.version_number}.",
        )

    # 3) Apply updates to all fields, including recurrence_rule/recurrence_end
    if event_in.title is not None:
        event.title = event_in.title
    if event_in.description is not None:
        event.description = event_in.description
    if event_in.start_datetime is not None:
        event.start_datetime = event_in.start_datetime
    if event_in.end_datetime is not None:
        event.end_datetime = event_in.end_datetime

    # New: recurrence updates
    event.recurrence_rule = event_in.recurrence_rule
    event.recurrence_end = event_in.recurrence_end

    # 4) Bump version_number
    event.version_number += 1
    db.add(event)
    await db.commit()
    await db.refresh(event)

    # 5) Record a new version snapshot
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