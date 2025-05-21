from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime

from ..models import Event, User, EventPermission
from ..schemas import UserRead, PermissionRead  # to return user info in list
from ..db.session import get_db
from ..dependencies import get_current_user

router = APIRouter(prefix="/api/events", tags=["permissions"])


@router.post("/{event_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def share_event(
    event_id: int,
    user_id: int,
    can_edit: bool,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Grant or update permission on an event.
    Only the event owner (creator) can share.
    """
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event or event.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # Prevent sharing to oneself
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot share event with yourself",
        )

    # Verify target user exists
    user_result = await db.execute(select(User).where(User.id == user_id))
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Upsert permission
    perm_result = await db.execute(
        select(EventPermission).where(
            EventPermission.event_id == event_id, EventPermission.user_id == user_id
        )
    )
    perm = perm_result.scalar_one_or_none()
    if perm:
        perm.can_edit = can_edit
        perm.granted_by_id = current_user.id
        perm.granted_at = datetime.utcnow()
    else:
        perm = EventPermission(
            event_id=event_id,
            user_id=user_id,
            can_edit=can_edit,
            granted_by_id=current_user.id,
            granted_at=datetime.utcnow(),
        )
        db.add(perm)

    await db.commit()
    return None  # 204 No Content


@router.get(
    "/{event_id}/permissions",
    response_model=List[PermissionRead],
)
async def list_permissions(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    List all users who have any permission on this event.
    Only owner or any user with a permission (read or edit) can view the list.
    """
    ev = await db.execute(select(Event).where(Event.id == event_id))
    event = ev.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # Check read access: owner or someone in event_permissions
    if event.creator_id != current_user.id:
        perm_res = await db.execute(
            select(EventPermission).where(
                EventPermission.event_id == event_id,
                EventPermission.user_id == current_user.id,
            )
        )
        if not perm_res.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    # Fetch all permission rows and join with User
    perms = await db.execute(
        select(
            User.id.label("id"),
            User.username.label("username"),
            EventPermission.can_edit.label("can_edit"),
            EventPermission.granted_at.label("granted_at"),
        )
        .join(EventPermission, EventPermission.user_id == User.id)
        .where(EventPermission.event_id == event_id)
    )
    rows = perms.all()

    # Return a list of PermissionRead-compatible dicts
    shared = [
        {
            "id": row.id,
            "username": row.username,
            "can_edit": row.can_edit,
            "granted_at": row.granted_at if row and row.granted_at else None,
        }
        for row in rows
    ]
    
    # Fetch the event again (or reuse earlier query) to get creator_id and username:
    # (You already have `event` and `current_user` from the auth check.)
    owner_entry = {
        "id": event.creator_id,
        "username": current_user.username,  # or query User separately
        "can_edit": True,
        "granted_at": None,  # or event.created_at if you prefer
    }

    return [owner_entry] + shared


@router.delete("/{event_id}/permissions/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_permission(
    event_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Revoke a shared permission.
    Only the owner (creator) can revoke.
    """
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event or event.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    perm_result = await db.execute(
        select(EventPermission).where(
            EventPermission.event_id == event_id, EventPermission.user_id == user_id
        )
    )
    perm = perm_result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")

    await db.delete(perm)
    await db.commit()
    return None  # 204 No Content
