from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func

from datetime import datetime

from slowapi import Limiter
from slowapi.util import get_remote_address

from ..models import Event, User, EventPermission
from ..schemas import UserRead, PermissionRead  # to return user info in list
from ..db.session import get_db
from ..dependencies import get_current_user
from ..schemas import EventShare

router = APIRouter(prefix="/api/events", tags=["permissions"])

# If you want a dedicated limiter instead of re-importing the global one:
limiter = Limiter(key_func=get_remote_address)

@router.post("/{event_id}/share", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def share_event(
    event_id: int,
    request: Request,
    payload: EventShare,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Grant a user permission on `event_id`. Only the event's creator may share.
    Expects JSON body:
        {
          "user_id": 123,
          "can_edit": true
        }
    """
    # 1) Verify that the event exists
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # 2) Only the event’s creator can “share” it
    if event.creator_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the event creator can share this event"
        )

    # 3) Verify the target user exists
    user_result = await db.execute(select(User).where(User.id == payload.user_id))
    target = user_result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Target user does not exist")

    # 4) If a permission row already exists, update its can_edit flag; otherwise create one
    existing_perm = (
        await db.execute(
            select(EventPermission).where(
                (EventPermission.event_id == event_id)
                & (EventPermission.user_id == payload.user_id)
            )
        )
    ).scalar_one_or_none()

    if existing_perm:
        existing_perm.can_edit = payload.can_edit
        existing_perm.granted_by_id = current_user.id
        existing_perm.granted_at = func.now()
    else:
        new_perm = EventPermission(
            event_id=event_id,
            user_id=payload.user_id,
            can_edit=payload.can_edit,
            granted_by_id=current_user.id,
        )
        db.add(new_perm)

    await db.commit()
    return {"detail": "Permission granted/updated successfully"}


@router.get(
    "/{event_id}/permissions",
    response_model=List[PermissionRead],
)
@limiter.limit("20/minute")
async def list_permissions(
    event_id: int,
    request: Request,
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
@limiter.limit("20/minute")
async def revoke_permission(
    event_id: int,
    user_id: int,
    request: Request,
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


@router.put(
    "/{event_id}/permissions/{user_id}",
    response_model=PermissionRead,
)
@limiter.limit("20/minute")
async def update_permission(
    event_id: int,
    user_id: int,
    can_edit: bool,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Update an existing permission’s can_edit flag (only owner can do this).
    Returns the updated PermissionRead.
    """
    # 1) Verify the event exists & current_user is owner
    ev = await db.execute(select(Event).where(Event.id == event_id))
    event = ev.scalar_one_or_none()
    if not event or event.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # 2) Find the existing permission
    perm_res = await db.execute(
        select(EventPermission).where(
            EventPermission.event_id == event_id,
            EventPermission.user_id == user_id,
        )
    )
    perm = perm_res.scalar_one_or_none()
    if not perm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found for this user",
        )

    # 3) Update fields
    perm.can_edit = can_edit
    perm.granted_by_id = current_user.id
    perm.granted_at = datetime.utcnow()
    db.add(perm)
    await db.commit()
    # No need to refresh perm for username—fetch it explicitly below

    # 4) Fetch username directly, to avoid lazy‐loading
    user_res = await db.execute(select(User.username).where(User.id == user_id))
    username = user_res.scalar_one_or_none()
    if username is None:
        # In the unlikely case the user no longer exists
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found after updating permission",
        )

    return {
        "id": user_id,
        "username": username,
        "can_edit": perm.can_edit,
        "granted_at": perm.granted_at,
    }