import redis.asyncio as redis
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from redis.exceptions import RedisError
import logging

from .routers import auth, events, permissions, versions, websocket, test, health
from .middleware.msgpack import msgpack_or_json
from .middleware.audit import AuditMiddleware
from .core.logging import setup_logging

redis_url = "redis://localhost:6379/0"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan handler (replaces deprecated @app.on_event("startup")).
    """
    # Setup logging
    setup_logging()
    logger.info("Starting application...")

    try:
        redis_client = redis.from_url(redis_url, encoding="utf8", decode_responses=True)
        await redis_client.ping()
        FastAPICache.init(RedisBackend(redis_client), prefix="fastapi-cache")
        logger.info("Successfully connected to Redis")
    except RedisError as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        raise

    yield

    logger.info("Shutting down application...")
    await redis_client.close()

# Initialize FastAPI with custom error handlers and middleware
app = FastAPI(
    title="NeoFi Event Management API",
    description="Collaborative Event Management System with versioning",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# Add middlewares
from .middleware.request_logging import RequestLoggingMiddleware
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(AuditMiddleware)

# MessagePack middleware
app.middleware("http")(msgpack_or_json)

# Rate limiting setup (slowapi)
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

# Include routers
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(permissions.router)
app.include_router(versions.router)
app.include_router(websocket.router)
app.include_router(test.router)
app.include_router(health.router)

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
