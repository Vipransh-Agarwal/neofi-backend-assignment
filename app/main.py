import redis.asyncio as aioredis
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from redis.exceptions import RedisError

from .routers import auth, events, permissions, versions
from .middleware.msgpack import msgpack_or_json
from .middleware.audit import AuditMiddleware

redis_url = "redis://localhost:6379/0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan handler (replaces deprecated @app.on_event("startup")).
    """
    # ─── Startup ───────────────────────────────────────────────────────────────
    # Use redis.asyncio instead of aioredis package
    redis_client = aioredis.from_url(redis_url, encoding="utf8", decode_responses=True)
    FastAPICache.init(RedisBackend(redis_client), prefix="fastapi-cache")

    yield  # Now FastAPI will run and serve requests

    # ─── Shutdown ──────────────────────────────────────────────────────────────
    await redis_client.close()


# Create the FastAPI app with our lifespan
app = FastAPI(lifespan=lifespan)

# Rate limiting setup (slowapi)
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

# MessagePack middleware
app.middleware("http")(msgpack_or_json)

# Audit logging middleware
app.add_middleware(AuditMiddleware)

# Include routers
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(permissions.router)
app.include_router(versions.router)

# Add error handlers
@app.exception_handler(RedisError)
async def redis_exception_handler(request, exc):
    return JSONResponse(
        status_code=503,
        content={"detail": "Cache service temporarily unavailable"}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
