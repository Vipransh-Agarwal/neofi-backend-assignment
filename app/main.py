from fastapi import FastAPI
from .routers import auth, events, permissions, versions

app = FastAPI(
    title="NeoFi Collaborative Event API",
    version="0.2.0",
    description="Day 2: Permissions & Versioning"
)

app.include_router(auth.router)
app.include_router(events.router)
app.include_router(permissions.router)
app.include_router(versions.router)
