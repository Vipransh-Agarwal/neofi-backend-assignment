from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models import Event, EventPermission, EventVersion
from ..db.session import get_db
from ..dependencies import get_current_user

router = APIRouter(prefix="/api/events", tags=["versions"])


@router.get("/{event_id}/versions", response_model=List[Dict[str, Any]])
async def list_versions(
    event_id: int,
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


@router.get("/{event_id}/versions/{version_number}", response_model=Dict[str, Any])
async def get_version(
    event_id: int,
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


@router.get("/{event_id}/versions/{older}/diff/{newer}", response_model=List[Dict[str, Any]])
async def get_diff(
    event_id: int,
    older: int,
    newer: int,
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
