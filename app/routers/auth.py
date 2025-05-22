from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from slowapi import Limiter
from slowapi.util import get_remote_address

from ..schemas import UserCreate, UserRead, Token, RefreshToken
from ..models import User
from ..db.session import get_db
from ..core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_token,
)
from ..dependencies import get_current_user
from ..models import RoleType

# We only need OAuth2PasswordBearer for the logout endpoint:
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

router = APIRouter(prefix="/api/auth", tags=["auth"])

# If you want a dedicated limiter instead of re-importing the global one:
limiter = Limiter(key_func=get_remote_address)

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def register_user(
    user_in: UserCreate, 
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(User).where(
            (User.username == user_in.username) | (User.email == user_in.email)
        )
    )
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    # Get first user count to determine if this is the first user
    result = await db.execute(select(func.count(User.id)))
    user_count = result.scalar()

    # First user is automatically OWNER, otherwise use requested role or default VIEWER
    role = RoleType.OWNER if user_count == 0 else user_in.role

    hashed_pw = get_password_hash(user_in.password)
    new_user = User(
        username=user_in.username,
        email=user_in.email,
        password_hash=hashed_pw,
        role=role
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.post("/login", response_model=Token)
@limiter.limit("20/minute")
async def login_for_tokens(user_in: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user_in.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(user_in.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    data = {"sub": str(user.id)}
    access_token = create_access_token(data=data)
    refresh_token = create_refresh_token(data=data)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
    }


@router.post("/refresh", response_model=Token)
@limiter.limit("20/minute")
async def refresh_access_token(
    request: Request,
    refresh_token: RefreshToken,  # Expect JSON body: { "refresh_token": "..." }
):
    """
    Exchange a valid refresh token for a new access token and a new refresh token.
    """
    try:
        payload = decode_token(refresh_token.refresh_token, expected_type="refresh")
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalid or expired",
        )

    # Revoke the old refresh token so it can’t be used again
    revoke_token(refresh_token.refresh_token)

    data = {"sub": str(user_id)}
    new_access = create_access_token(data=data)
    new_refresh = create_refresh_token(data=data)
    return {"access_token": new_access, "token_type": "bearer", "refresh_token": new_refresh}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def logout_current_token(
    request: Request,
    access_token: str = Depends(oauth2_scheme),
    # Optionally accept a JSON body with { "refresh_token": "..." } to revoke that too
    refresh_token: RefreshToken | None = None,
):
    """
    Invalidate the current access token. Optionally revoke a provided refresh token.
    """
    # Revoke the access token (we know it’s a valid access token because get_current_user was already used
    # if you want to double-check, you could call decode_token(access_token, "access") again)
    revoke_token(access_token)

    # If a refresh_token was provided, revoke it as well
    if refresh_token and refresh_token.refresh_token:
        revoke_token(refresh_token.refresh_token)

    return None


@router.get("/me", response_model=UserRead)
@limiter.limit("20/minute")
async def read_users_me(request: Request, current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/users/{user_id}/role")
@limiter.limit("20/minute")
async def update_user_role(
    user_id: int,
    new_role: RoleType,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)  # Only OWNER can change roles
):
    """
    Update a user's role. Only OWNER can perform this action.
    
    Rules:
    1. Only OWNER can change roles
    2. OWNER cannot change their own role
    3. Cannot create new OWNER roles
    4. Must always have at least one OWNER in the system
    """
    # Check if trying to modify own role
    if current_user.id == user_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot modify your own role"
        )
    
    # Prevent creating new OWNER roles
    if new_role == RoleType.OWNER:
        raise HTTPException(
            status_code=400,
            detail="Cannot set OWNER role for other users"
        )
        
    # Get target user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update role
    user.role = new_role
    await db.commit()
    await db.refresh(user)
    
    return {
        "message": f"Role updated successfully",
        "user_id": user.id,
        "username": user.username,
        "old_role": user.role,
        "new_role": new_role
    }
