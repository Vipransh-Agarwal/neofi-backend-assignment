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
