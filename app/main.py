from fastapi import FastAPI

from .routers import auth  # Adjust if your import path is different
from fastapi.security import OAuth2PasswordBearer


app = FastAPI(
    title="NeoFi Collaborative Event API",
    version="0.1.0",
    description="Backend for Day 1 Step 2: User Authentication"
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Include the auth router
app.include_router(auth.router)