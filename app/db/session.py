import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Read the DATABASE_URL from the environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable must be set")

# Create the async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,      # set to True if you want SQL logging
    future=True,
    pool_size=20,    # Maximum number of connections in the pool
    max_overflow=10, # Maximum number of connections that can be created beyond pool_size
    pool_timeout=30, # Timeout for getting a connection from the pool
    pool_pre_ping=True, # Enable connection health checks
)

# Create a session factory bound to the async engine
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# Dependency to get an AsyncSession in FastAPI endpoints
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
