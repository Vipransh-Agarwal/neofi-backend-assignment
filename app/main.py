from fastapi import FastAPI
from .routers import auth, events

app = FastAPI(
    title="NeoFi Collaborative Event API",
    version="0.1.0",
    description="Day 1 Step 3: Event creation"
)

app.include_router(auth.router)
app.include_router(events.router)
