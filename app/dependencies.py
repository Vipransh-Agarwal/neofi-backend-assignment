import os
from fastapi import Depends, HTTPException, status, WebSocket
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from typing import Optional, List

from .models import User, Event, EventPermission, RoleType
from .db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from .core.security import decode_access_token  # uses Redis internally

# Correct the tokenUrl so Swagger’s OAuth UI points to /api/auth/login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token is invalid/expired",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return user

async def check_event_permission(
    event_id: int,
    required_role: RoleType,
    user: User,
    db: AsyncSession
) -> bool:
    """
    Check if user has required role-based permission for an event
    """
    # Get the event
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    # Owner of the event has full access
    if event.creator_id == user.id:
        return True
        
    # Check user's role and explicit permissions
    if user.role == RoleType.OWNER:
        return True
        
    # For editors
    if required_role == RoleType.VIEWER and user.role in [RoleType.EDITOR, RoleType.OWNER]:
        return True
        
    # Check explicit event permissions
    result = await db.execute(
        select(EventPermission).where(
            (EventPermission.event_id == event_id) &
            (EventPermission.user_id == user.id)
        )
    )
    permission = result.scalar_one_or_none()
    
    if permission:
        if required_role == RoleType.VIEWER:
            return True
        elif required_role == RoleType.EDITOR and permission.can_edit:
            return True
            
    return False

def require_role(required_role: RoleType):
    """
    Dependency factory for requiring specific role access to endpoints
    """
    async def role_checker(
        event_id: Optional[int] = None,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ):
        # For non-event specific endpoints, just check the role
        if event_id is None:
            if user.role == RoleType.OWNER:
                return True
            if required_role == RoleType.VIEWER and user.role in [RoleType.VIEWER, RoleType.EDITOR, RoleType.OWNER]:
                return True
            if required_role == RoleType.EDITOR and user.role in [RoleType.EDITOR, RoleType.OWNER]:
                return True
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {required_role.value} required"
            )
        
        # For event-specific endpoints, check both role and permissions
        has_permission = await check_event_permission(event_id, required_role, user, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return True
        
    return role_checker

from fastapi import Security, HTTPException

def check_roles(allowed_roles: List[RoleType]):
    async def role_checker(user: User = Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role {user.role} not authorized. Required: {[r.value for r in allowed_roles]}"
            )
        return user
    return role_checker

# Convenience dependencies for common role combinations
require_owner = check_roles([RoleType.OWNER])
require_editor_or_above = check_roles([RoleType.OWNER, RoleType.EDITOR])
require_any_role = check_roles([RoleType.OWNER, RoleType.EDITOR, RoleType.VIEWER])

async def get_current_user_ws(
    websocket: WebSocket,
    token: str = None
):
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
        
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
        return user_id
    except:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None