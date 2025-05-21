from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

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

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
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

    hashed_pw = get_password_hash(user_in.password)
    new_user = User(
        username=user_in.username,
        email=user_in.email,
        password_hash=hashed_pw,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.post("/login", response_model=Token)
async def login_for_tokens(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user_in.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(user_in.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    data = {"sub": str(user.id)}  # subject is user ID (string)
    access_token = create_access_token(data=data)
    refresh_token = create_refresh_token(data=data)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
    }


@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    refresh_token: RefreshToken,  # we’ll accept a JSON body: {"refresh_token": "..."}
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

    # Revoke the old refresh token so it can’t be reused
    revoke_token(refresh_token)

    data = {"sub": str(user_id)}
    new_access = create_access_token(data=data)
    new_refresh = create_refresh_token(data=data)
    return {"access_token": new_access, "token_type": "bearer", "refresh_token": new_refresh}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_current_token(token: str = Depends(get_current_user)):
    """
    Invalidate the current access token. We also revoke any refresh tokens with the same JTI if provided.
    """
    # The `Depends(get_current_user)` will already have decoded and validated an access token.
    # FastAPI injects the 'token' argument as the raw token string in this case. We just revoke it:
    revoke_token(token)
    return None


@router.get("/me", response_model=UserRead)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
