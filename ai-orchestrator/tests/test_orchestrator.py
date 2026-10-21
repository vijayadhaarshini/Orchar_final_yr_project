"""Tests for the orchestration engine and API routes.

These tests use mocked agents so they don't require a live LLM connection
or a real database – they verify the wiring and control flow.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.core import (
    AgentExecutionRead,
    FeatureRequest,
    PipelineRunRead,
    PipelineStartResponse,
    PlannerOutput,
    PlannerTaskItem,
    ProjectCreate,
    TestResult,
)

# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestSchemas:
    """Verify that Pydantic schemas accept valid data and reject invalid data."""

    def test_project_create_valid(self):
        p = ProjectCreate(name="Test", description="desc")
        assert p.name == "Test"

    def test_project_create_missing_name(self):
        with pytest.raises(ValidationError):
            ProjectCreate(description="no name")

    def test_feature_request_valid(self):
        f = FeatureRequest(request_type="feature", description="Build X")
        assert f.request_type == "feature"

    def test_feature_request_invalid_type(self):
        with pytest.raises(ValidationError):
            FeatureRequest(request_type="invalid", description="Build X")

    def test_feature_request_default_type(self):
        f = FeatureRequest(description="Build X")
        assert f.request_type == "feature"

    def test_planner_output(self):
        po = PlannerOutput(tasks=[
            PlannerTaskItem(id="1", description="Do A", priority="high"),
            PlannerTaskItem(id="2", description="Do B", priority="low"),
        ])
        assert len(po.tasks) == 2

    def test_test_result(self):
        tr = TestResult(status="pass", coverage=95.0)
        assert tr.errors is None

    def test_pipeline_start_response(self):
        r = PipelineStartResponse(run_id=42, status="pending")
        assert r.run_id == 42

    def test_pipeline_run_read(self):
        from datetime import UTC, datetime
        r = PipelineRunRead(
            id=1, project_id=1, feature_description="X",
            request_type="feature", status="completed",
            created_at=datetime.now(UTC),
        )
        assert r.status == "completed"

    def test_agent_execution_read(self):
        from datetime import UTC, datetime
        e = AgentExecutionRead(
            id=1, project_id=1, agent_name="planner",
            status="completed", created_at=datetime.now(UTC),
        )
        assert e.execution_time == 0.0
        assert e.tokens_used == 0


# ---------------------------------------------------------------------------
# Orchestration error
# ---------------------------------------------------------------------------


class TestOrchestrationError:
    def test_error_attributes(self):
        from app.orchestrator.service import OrchestrationError
        err = OrchestrationError("planner", "timeout")
        assert err.agent_name == "planner"
        assert err.message == "timeout"
        assert str(err) == "timeout"


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfig:
    def test_settings_load(self):
        """Verify settings can be instantiated (uses .env or defaults)."""
        from app.config import settings
        assert settings.APP_NAME == "AI Orchestrator"
        assert settings.AGENT_MAX_RETRIES == 2

    def test_cors_origins_default(self):
        from app.config import settings
        assert "http://localhost:5173" in settings.cors_origins

    def test_cors_origins_comma_separated(self, monkeypatch):
        from app.config import Settings
        monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://a.test, http://b.test")
        assert Settings().cors_origins == ["http://a.test", "http://b.test"]


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------


class TestStartBackground:
    @pytest.mark.asyncio
    async def test_task_runs_and_is_released(self):
        import asyncio

        from app.utils import execution

        done = asyncio.Event()

        async def work():
            done.set()

        task = execution.start_background(work(), name="test-task")
        assert task in execution._running_tasks  # held while running
        await task
        assert done.is_set()
        assert task not in execution._running_tasks  # released when finished

    @pytest.mark.asyncio
    async def test_crash_is_logged_not_lost(self, monkeypatch):
        import asyncio

        from app.utils import execution

        logged = []
        monkeypatch.setattr(execution, "log_structured", lambda event, **kw: logged.append(event))

        async def boom():
            raise RuntimeError("bad")

        task = execution.start_background(boom(), name="crashing-task")
        await asyncio.gather(task, return_exceptions=True)
        assert logged == ["background_task_crashed"]


class TestLogging:
    def test_log_structured_no_crash(self):
        from app.utils.logging import log_structured
        log_structured("test_event", key="value", number=42)

    def test_configure_logging(self):
        from app.utils.logging import configure_logging
        configure_logging()  # should not raise


# ---------------------------------------------------------------------------
# Sandbox utility tests
# ---------------------------------------------------------------------------


class TestSandboxUtility:
    def test_sandbox_pass(self):
        from app.utils.sandbox import run_pytest
        code = "def greet():\n    return 'hello'"
        tests = "from solution import greet\n\ndef test_greet():\n    assert greet() == 'hello'"
        assert run_pytest(code, tests, module_name="solution", timeout=30).passed

    def test_sandbox_fail(self):
        from app.utils.sandbox import run_pytest
        code = "def greet():\n    return 'wrong'"
        tests = "from solution import greet\n\ndef test_greet():\n    assert greet() == 'hello'"
        assert run_pytest(code, tests, module_name="solution", timeout=30).passed is False

    def test_sandbox_syntax_error(self):
        from app.utils.sandbox import run_pytest
        result = run_pytest("def broken(:", "def test_x():\n    pass", timeout=30)
        assert result.passed is False

    def test_secrets_are_not_passed_to_generated_code(self, monkeypatch):
        from app.utils.sandbox import run_pytest
        monkeypatch.setenv("GROQ_API_KEY", "secret-value")
        code = "import os\nKEY = os.environ.get('GROQ_API_KEY')"
        tests = "from module_under_test import KEY\n\ndef test_no_key():\n    assert KEY is None"
        assert run_pytest(code, tests, timeout=30).passed

    def test_missing_package_is_faked_not_installed(self):
        from app.utils.sandbox import missing_modules, run_pytest
        code = "import surely_not_a_real_pkg_123\n\ndef f():\n    return 1"
        assert missing_modules(code) == ["surely_not_a_real_pkg_123"]
        tests = "from module_under_test import f\n\ndef test_f():\n    assert f() == 1"
        assert run_pytest(code, tests, timeout=30).passed
