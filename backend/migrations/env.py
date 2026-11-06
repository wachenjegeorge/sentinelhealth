import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Priority: MIGRATION > ADMIN > DATABASE
db_url = (
    os.getenv("DATABASE_URL_MIGRATION")
    or os.getenv("DATABASE_URL_ADMIN")
    or os.getenv("DATABASE_URL")
    or "postgresql+asyncpg://sentinel:change-me@localhost:5432/sentinel"
)

# Print a redacted version so we can verify which URL is being used
def redact(url: str) -> str:
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.split("@", 1)
        user = creds.split(":")[0] if ":" in creds else creds
        return f"{scheme}://{user}:***@{host}"
    return url

print(f"[alembic] Using database URL: {redact(db_url)}")
config.set_main_option("sqlalchemy.url", db_url)
target_metadata = Base.metadata


def do_run(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async():
    eng = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with eng.connect() as c:
        await c.run_sync(do_run)
    await eng.dispose()


if context.is_offline_mode():
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_async())
