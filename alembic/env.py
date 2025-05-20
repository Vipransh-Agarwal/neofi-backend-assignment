# alembic/env.py
import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# 1) Optional: If you have a .env file at the project root, load it
#    (uncomment if you use python-dotenv)
# from dotenv import load_dotenv
# dotenv_path = os.path.join(os.getcwd(), ".env")
# if os.path.isfile(dotenv_path):
#     load_dotenv(dotenv_path)

# 2) Read DATABASE_URL from the environment
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL environment variable is not set")

# 3) Make sure the project’s `app/` directory is on sys.path so we can import models
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "app")))
from models import Base  # noqa: E402

# 4) Alembic Config object
config = context.config

# 5) Override the sqlalchemy.url option so Alembic knows where to connect
config.set_main_option("sqlalchemy.url", database_url)

# 6) (Optional) Set up logging based on the [loggers]/[handlers]/[formatters] in alembic.ini
fileConfig(config.config_file_name)

# 7) Provide your metadata for 'autogenerate' support
target_metadata = Base.metadata

def run_migrations_offline():
    """Run migrations in 'offline' mode (generating SQL without DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in 'online' mode with an async engine."""
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    # Note: do_run_migrations must be sync, since run_sync expects a sync callable
    def do_run_migrations(connection: Connection):
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    async def run_async_migrations():
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
