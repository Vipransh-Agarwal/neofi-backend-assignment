from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any
from enum import Enum

# ─── User schemas ──────────────────────────────────────────────────────────

class RoleType(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: Optional[RoleType] = RoleType.VIEWER  # Add this line

class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: datetime
    role: RoleType  # Add this line

    class Config:
        orm_mode = True


# ─── Token schemas ─────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str

class RefreshToken(BaseModel):
    refresh_token: str

class TokenPayload(BaseModel):
    sub: int          # user ID
    exp: int          # expiration timestamp (Unix epoch)
    

# ─── Event schemas ─────────────────────────────────────────────────────────


class EventBase(BaseModel):
    title: str
    description: Optional[str]
    start_datetime: datetime
    end_datetime: datetime
    recurrence_rule: Optional[str] = None
    recurrence_end: Optional[datetime] = None
    
    model_config = {"from_attributes": True}

class EventCreate(EventBase):
    pass

class EventRead(EventBase):
    id: int
    creator_id: int
    version_number: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class EventUpdate(BaseModel):
    # When updating, client must supply the version_number they last saw
    title: Optional[str] = None
    description: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    recurrence_rule: Optional[str] = None
    recurrence_end: Optional[datetime] = None
    # version_number: int
    
    model_config = {"from_attributes": True}

class EventBatchCreate(BaseModel):
    events: List[EventCreate]


class EventVersionRead(BaseModel):
    version_number: int
    snapshot: Any
    created_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}

class EventShare(BaseModel):
    user_id: int
    can_edit: bool
    
    model_config = {"from_attributes": True}

class EventConflict(BaseModel):
    id: int
    title: str
    start: datetime
    end: datetime
    
    model_config = {"from_attributes": True}

class ConflictResponse(BaseModel):
    message: str
    conflicts: List[EventConflict]

    model_config = {"from_attributes": True}



# ─── Permission schemas ─────────────────────────────────────────────────────────

class PermissionRead(BaseModel):
    id: int                   # user_id
    username: str
    can_edit: bool
    granted_at: Optional[datetime]  # allow None

    class Config:
        orm_mode = True