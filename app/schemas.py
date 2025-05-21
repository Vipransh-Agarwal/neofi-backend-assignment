from datetime import datetime
from pydantic import BaseModel, EmailStr

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