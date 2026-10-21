"""Pause/resume tests for the pipeline.

The agents are fakes (see conftest.py), so these tests check the control
flow: which stages run, where a run pauses, and where it continues.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.orchestrator import service
from tests.conftest import get_run, new_run

# The same stage appears twice. Resuming must continue from the right copy.
REPEATED_STAGE_PLAN = {
    "stages": ["developer", "tester", "developer", "tester", "self_evolve"],
    "checkpoints": ["after_tester"],
    "skip": [],
    "reason": "test",
}


@pytest.mark.asyncio
async def test_repeated_stage_resumes_at_the_right_place_and_finishes(session_factory, fake_agents):
    """The plan has "tester" twice. Before the fix, resuming after the
    second tester jumped back to the first one and looped forever."""
    fake_agents["overseer"].return_value = REPEATED_STAGE_PLAN
    run_id = await new_run(session_factory)
    project_id = (await get_run(session_factory, run_id)).project_id

    # 1st call: developer, first tester, then pauses.
    await service.run_pipeline_background(run_id, project_id)
    run = await get_run(session_factory, run_id)
    assert (run.status, run.next_stage_index) == ("awaiting_human", 2)

    # 2nd call: developer again, second tester, then pauses again.
    await service.run_pipeline_background(run_id, project_id)
    run = await get_run(session_factory, run_id)
    assert (run.status, run.next_stage_index) == ("awaiting_human", 4)
    assert run.test_result["status"] == "pass"  # saved at the pause, not lost

    # 3rd call: self_evolve, then done.
    await service.run_pipeline_background(run_id, project_id)
    run = await get_run(session_factory, run_id)
    assert run.status == "completed"
    assert run.next_stage_index == 5  # every stage finished
    assert run.test_result["status"] == "pass"
    assert fake_agents["tester"].await_count == 2  # once per tester stage, no loop


@pytest.mark.asyncio
async def test_server_restart_fails_runs_that_were_cut_off(session_factory):
    running = await new_run(session_factory, status="developing", current_agent="developer")
    paused = await new_run(session_factory, status="awaiting_human")
    finished = await new_run(session_factory, status="completed", current_agent="designing")

    assert await service.fail_interrupted_runs() == 1
    assert (await get_run(session_factory, running)).status == "failed"
    assert (await get_run(session_factory, paused)).status == "awaiting_human"
    assert (await get_run(session_factory, finished)).current_agent == ""


@pytest.mark.asyncio
async def test_approving_twice_only_resumes_once(api_db, monkeypatch):
    from app.api import routes
    from app.main import app

    run_id = await new_run(api_db, status="awaiting_human", checkpoint_stage="after_tester")
    project_id = (await get_run(api_db, run_id)).project_id

    started = MagicMock()
    monkeypatch.setattr(routes, "start_background", started)
    monkeypatch.setattr(routes, "run_pipeline_background", MagicMock())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        url = f"/project/{project_id}/pipeline/{run_id}/checkpoint/respond"
        first = await client.post(url, json={"action": "approve"})
        second = await client.post(url, json={"action": "approve"})

    assert first.status_code == 200 and first.json()["status"] == "resuming"
    assert second.status_code == 409
    assert started.call_count == 1
