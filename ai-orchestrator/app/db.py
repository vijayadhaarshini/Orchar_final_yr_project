from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Columns added after the first release. `create_all` does not change tables
# that already exist, so older databases get these columns here instead.
# Each statement is safe to run on every startup.
_ADD_MISSING_COLUMNS = (
    "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS execution_time DOUBLE PRECISION NOT NULL DEFAULT 0.0",
    "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS tokens_used INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS priority VARCHAR(20) NOT NULL DEFAULT 'medium'",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS persona VARCHAR(50) NOT NULL DEFAULT 'intermediate'",
    "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS design_artifact TEXT DEFAULT ''",
    "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS persona VARCHAR(50) NOT NULL DEFAULT 'intermediate'",
    "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS overseer_plan JSONB DEFAULT NULL",
    "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS checkpoint_stage VARCHAR(100) DEFAULT NULL",
    "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS checkpoint_prompt TEXT DEFAULT NULL",
    "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS next_stage_index INTEGER DEFAULT NULL",
    "ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS pipeline_run_id INTEGER "
    "REFERENCES pipeline_runs(id) ON DELETE CASCADE",
    "CREATE INDEX IF NOT EXISTS ix_agent_executions_pipeline_run_id ON agent_executions (pipeline_run_id)",
)


async def init_db() -> None:
    """Create missing tables and columns."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for statement in _ADD_MISSING_COLUMNS:
            await conn.execute(text(statement))
