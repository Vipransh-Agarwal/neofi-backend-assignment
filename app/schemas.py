from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional, List

# ─── User schemas ──────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: datetime

    class Config:
        orm_mode = True


# ─── Token schemas ─────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str   # e.g. "bearer"

class TokenPayload(BaseModel):
    sub: int          # user ID
    exp: int          # expiration timestamp (Unix epoch)
    

# ─── Event schemas ─────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_datetime: datetime
    end_datetime: datetime

class EventRead(BaseModel):
    id: int
    title: str
    description: Optional[str]
    start_datetime: datetime
    end_datetime: datetime
    creator_id: int
    created_at: datetime

    class Config:
        orm_mode = True


class EventUpdate(BaseModel):
    title:    Optional[str] = None
    description: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime:   Optional[datetime] = None

class EventBatchCreate(BaseModel):
    events: List[EventCreate]



# ─── Permission schemas ─────────────────────────────────────────────────────────

class PermissionRead(BaseModel):
    id: int                   # user_id
    username: str
    can_edit: bool
    granted_at: Optional[datetime]  # allow None

    class Config:
        orm_mode = True