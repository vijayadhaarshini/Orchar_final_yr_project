"""Shared test setup: safe settings, an in-memory database and fake agents.

With these, the tests run without Postgres, without an API key and
without calling an LLM.
"""

from __future__ import annotations

import os
import tempfile

# These must be set before anything from `app` is imported, because the
# settings are read at import time. Real environment values and the .env
# file are overridden on purpose: tests must never touch real services.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["GROQ_API_KEY"] = "test-key-not-real"
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="orchar_test_chroma_")

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_db
from app.main import app
from app.models.core import PipelineRun, Project
from app.orchestrator import service
from app.schemas.core import TestResult

FAKE_TESTS = "def test_fixed():\n    assert True\n"


@pytest_asyncio.fixture
async def session_factory(monkeypatch):
    """A fresh SQLite database in memory, used in place of Postgres."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(service, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def api_db(session_factory):
    """Point the API at the in-memory database for one test."""

    async def test_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    yield session_factory
    app.dependency_overrides.clear()


@pytest.fixture
def fake_agents(monkeypatch):
    """Replace every agent and memory call the pipeline makes. Returns the fakes."""
    fakes = {
        "tester": AsyncMock(return_value=(TestResult(status="pass", coverage=90.0), FAKE_TESTS)),
        "developer": AsyncMock(return_value="def fixed():\n    return 1\n"),
        "critic": AsyncMock(return_value={"score": 9, "critique": "fine", "improved": "def fixed():\n    return 1\n"}),
        "overseer": AsyncMock(),
    }
    monkeypatch.setattr(service.tester_agent, "run", fakes["tester"])
    monkeypatch.setattr(service.developer_agent, "run", fakes["developer"])
    monkeypatch.setattr(service.critic_agent, "critique_code", fakes["critic"])
    monkeypatch.setattr(service.overseer_agent, "plan", fakes["overseer"])
    monkeypatch.setattr(service.self_evolve_agent, "learn", AsyncMock())
    monkeypatch.setattr(service, "load_evolved_prompts", lambda project_id: {})
    monkeypatch.setattr(service, "_build_context", AsyncMock(return_value=""))
    monkeypatch.setattr(service.vector_store, "add_documents", AsyncMock())
    return fakes


async def new_run(factory, **fields) -> int:
    """Save a project and a pipeline run, and return the run's id."""
    async with factory() as db:
        project = Project(name="demo")
        db.add(project)
        await db.flush()
        run = PipelineRun(project_id=project.id, feature_description="fix it",
                          request_type=fields.pop("request_type", "bug"), **fields)
        db.add(run)
        await db.commit()
        return run.id


async def get_run(factory, run_id: int) -> PipelineRun:
    async with factory() as db:
        return await db.get(PipelineRun, run_id)
