from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from datetime import datetime

from slowapi import Limiter
from slowapi.util import get_remote_address

from ..models import Event, EventPermission, EventVersion, EventChange
from ..schemas import EventVersionRead
from ..db.session import get_db
from ..dependencies import get_current_user
from ..utils.versioning import record_event_version

router = APIRouter(prefix="/api/events", tags=["versions"])

# If you want a dedicated limiter instead of re-importing the global one:
limiter = Limiter(key_func=get_remote_address)

@router.get("/{event_id}/history", response_model=List[Dict[str, Any]])
@limiter.limit("20/minute")
async def list_versions(
    event_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    List all versions for an event (owner or shared user can view).
    """
    ev = await db.execute(select(Event).where(Event.id == event_id))
    event = ev.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # Check read access
    if event.creator_id != current_user.id:
        perm_res = await db.execute(
            select(EventPermission).where(
                EventPermission.event_id == event_id,
                EventPermission.user_id == current_user.id,
            )
        )
        if not perm_res.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    vers = await db.execute(
        select(EventVersion)
        .where(EventVersion.event_id == event_id)
        .order_by(EventVersion.version_number)
    )
    versions = vers.scalars().all()
    return [
        {
            "version_number": v.version_number,
            "created_at": v.created_at,
            "created_by_id": v.created_by_id,
        }
        for v in versions
    ]


@router.get("/{event_id}/history/{version_number}", response_model=Dict[str, Any])
@limiter.limit("20/minute")
async def get_version(
    event_id: int,
    request: Request,
    version_number: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get a single version’s full snapshot (owner or shared user).
    """
    ev = await db.execute(select(Event).where(Event.id == event_id))
    event = ev.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # Check read access
    if event.creator_id != current_user.id:
        perm_res = await db.execute(
            select(EventPermission).where(
                EventPermission.event_id == event_id,
                EventPermission.user_id == current_user.id,
            )
        )
        if not perm_res.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    ver = await db.execute(
        select(EventVersion).where(
            EventVersion.event_id == event_id,
            EventVersion.version_number == version_number,
        )
    )
    version = ver.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    return {
        "version_number": version.version_number,
        "snapshot": version.snapshot,
        "created_at": version.created_at,
        "created_by_id": version.created_by_id,
    }


@router.get("/{event_id}/diff/{older}/{newer}", response_model=List[Dict[str, Any]])
@limiter.limit("20/minute")
async def get_diff(
    event_id: int,
    older: int,
    newer: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return a list of field‐level diffs between two versions.
    """
    ev = await db.execute(select(Event).where(Event.id == event_id))
    event = ev.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # Check read access
    if event.creator_id != current_user.id:
        perm_res = await db.execute(
            select(EventPermission).where(
                EventPermission.event_id == event_id,
                EventPermission.user_id == current_user.id,
            )
        )
        if not perm_res.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    # Fetch both versions
    res_old = await db.execute(
        select(EventVersion).where(
            EventVersion.event_id == event_id,
            EventVersion.version_number == older,
        )
    )
    v_old = res_old.scalar_one_or_none()
    res_new = await db.execute(
        select(EventVersion).where(
            EventVersion.event_id == event_id,
            EventVersion.version_number == newer,
        )
    )
    v_new = res_new.scalar_one_or_none()

    if not v_old or not v_new:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    diffs = []
    old_snapshot = v_old.snapshot
    new_snapshot = v_new.snapshot

    for key in new_snapshot.keys():
        old_val = old_snapshot.get(key)
        new_val = new_snapshot.get(key)
        if old_val != new_val:
            diffs.append({"field_name": key, "old_value": old_val, "new_value": new_val})

    return diffs


@router.post(
    "/{event_id}/rollback/{version_number}",
    response_model=Dict[str, Any],
)
@limiter.limit("20/minute")
async def rollback_event(
    event_id: int,
    version_number: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Roll back the live event to a prior version. Only owner or can_edit==True can do this.
    Returns the newly‐created version (snapshot) representing the rollback state.
    """
    # 1) Verify event exists
    ev = await db.execute(select(Event).where(Event.id == event_id))
    event = ev.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # 2) Check write permission (owner or can_edit)
    if event.creator_id != current_user.id:
        perm_res = await db.execute(
            select(EventPermission).where(
                EventPermission.event_id == event_id,
                EventPermission.user_id == current_user.id,
            )
        )
        perm = perm_res.scalar_one_or_none()
        if not perm or not perm.can_edit:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    # 3) Fetch the requested version
    ver_res = await db.execute(
        select(EventVersion).where(
            EventVersion.event_id == event_id,
            EventVersion.version_number == version_number,
        )
    )
    old_version = ver_res.scalar_one_or_none()
    if not old_version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    snapshot = old_version.snapshot  # this is a dict of strings
    # 4) Overwrite the live Event’s fields from snapshot
    event.title = snapshot.get("title")
    event.description = snapshot.get("description")
    # parse ISO datetimes:
    from dateutil import parser

    event.start_datetime = parser.isoparse(snapshot.get("start_datetime"))
    event.end_datetime = parser.isoparse(snapshot.get("end_datetime"))
    # We do not overwrite creator_id or created_at; we want to preserve original creation ownership.
    
    db.add(event)
    await db.flush()

    # 5) Record a brand‐new version (this will get version_number = old + 1)
    await db.refresh(event)
    new_ver = await record_event_version(db, event, current_user.id)
    await db.commit()

    return {
        "version_number": new_ver.version_number,
        "snapshot": new_ver.snapshot,
        "created_at": new_ver.created_at,
        "created_by_id": new_ver.created_by_id,
    }

@router.get(
    "/{event_id}/changelog",
    response_model=List[Dict[str, Any]],
)
@limiter.limit("20/minute")
async def get_changelog(
    event_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return a chronological log of all changes:
    for each version: { version_number, created_at, created_by_id, changes: [ { field_name, old_value, new_value, changed_at } ] }
    """
    # 1) Verify event exists & read access
    ev = await db.execute(select(Event).where(Event.id == event_id))
    event = ev.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if event.creator_id != current_user.id:
        perm_res = await db.execute(
            select(EventPermission).where(
                EventPermission.event_id == event_id,
                EventPermission.user_id == current_user.id,
            )
        )
        if not perm_res.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    # 2) Query all versions for this event, in ascending order
    vers_res = await db.execute(
        select(EventVersion)
        .where(EventVersion.event_id == event_id)
        .order_by(EventVersion.version_number)
    )
    versions = vers_res.scalars().all()

    changelog = []
    for v in versions:
        # Instead of v.changes, explicitly query EventChange
        changes_res = await db.execute(
            select(EventChange).where(EventChange.event_version_id == v.id).order_by(EventChange.id)
        )
        changes = [
            {
                "field_name": c.field_name,
                "old_value": c.old_value,
                "new_value": c.new_value,
                "changed_at": c.changed_at,
            }
            for c in changes_res.scalars().all()
        ]

        changelog.append(
            {
                "version_number": v.version_number,
                "created_at": v.created_at,
                "created_by_id": v.created_by_id,
                "changes": changes,
            }
        )

    return changelog


@router.get("/at", response_model=EventVersionRead)
@limiter.limit("20/minute")
async def get_version_as_of(
    event_id: int,
    request: Request,
    at: datetime = Query(..., description="ISO8601 timestamp"),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Return the snapshot of an event as it existed at time `at`.
    Equivalent to GET /api/events/{id}/history?at=..., but now lives under /versions/at.
    """
    # 1) Verify event exists & user can read
    ev = await db.execute(select(Event).where(Event.id == event_id))
    event = ev.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # permission checks omitted...

    # 2) Find latest version <= at
    vq = await db.execute(
        select(EventVersion)
        .where(
            (EventVersion.event_id == event_id)
            & (EventVersion.created_at <= at)
        )
        .order_by(desc(EventVersion.version_number))
        .limit(1)
    )
    version = vq.scalar_one_or_none()
    if not version:
        raise HTTPException(
            status_code=404,
            detail=f"No version at or before {at.isoformat()}",
        )

    return EventVersionRead.model_validate(version)