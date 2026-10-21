"""Tests for what individual stages do inside a run.

The agents are fakes (see conftest.py). Each test checks one rule.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.agents.planner import planner_agent
from app.models.core import Task
from app.orchestrator import service
from tests.conftest import FAKE_TESTS, get_run, new_run


async def _run_plan(factory, fake_agents, stages: list[str]) -> int:
    fake_agents["overseer"].return_value = {"stages": stages, "checkpoints": [], "skip": [], "reason": "test"}
    run_id = await new_run(factory, request_type="feature")
    await service.run_pipeline_background(run_id, (await get_run(factory, run_id)).project_id)
    return run_id


@pytest.mark.asyncio
async def test_critic_stage_does_not_repeat_the_debate_review(session_factory, fake_agents):
    run_id = await _run_plan(session_factory, fake_agents, ["developer", "critic", "tester"])

    run = await get_run(session_factory, run_id)
    assert run.status == "completed"
    assert fake_agents["critic"].await_count == 1  # only the debate round, not a second pass
    skipped = [e for e in run.execution_timeline if e.get("agent") == "critic" and e.get("status") == "skipped"]
    assert len(skipped) == 1


@pytest.mark.asyncio
async def test_generated_tests_are_saved_on_the_run(session_factory, fake_agents):
    run_id = await _run_plan(session_factory, fake_agents, ["developer", "tester"])
    assert (await get_run(session_factory, run_id)).test_code == FAKE_TESTS


@pytest.mark.asyncio
async def test_tester_is_skipped_when_there_is_no_code(session_factory, fake_agents):
    run_id = await _run_plan(session_factory, fake_agents, ["tester"])

    run = await get_run(session_factory, run_id)
    assert run.status == "completed"
    fake_agents["tester"].assert_not_awaited()
    assert run.execution_timeline[0] == {"agent": "tester", "status": "skipped", "reason": "No code to test yet."}


@pytest.mark.asyncio
async def test_failed_revision_keeps_the_last_good_code(session_factory, fake_agents, monkeypatch):
    good_code = "def fixed():\n    return 1\n"
    fake_agents["critic"].return_value = {"score": 2, "critique": "weak", "improved": good_code}
    monkeypatch.setattr(service.developer_agent, "revise", AsyncMock(side_effect=ValueError("not valid Python")))

    run_id = await _run_plan(session_factory, fake_agents, ["developer"])
    assert (await get_run(session_factory, run_id)).generated_code == good_code


@pytest.mark.asyncio
async def test_debate_rounds_are_recorded_and_linked_to_their_run(session_factory, fake_agents):
    from app.models.core import AgentExecution

    run_id = await _run_plan(session_factory, fake_agents, ["developer"])
    async with session_factory() as db:
        rows = (await db.execute(select(AgentExecution))).scalars().all()
    assert sorted(row.agent_name for row in rows) == ["critic", "developer"]
    assert {row.pipeline_run_id for row in rows} == {run_id}


@pytest.mark.asyncio
async def test_failed_stage_is_where_the_run_stopped(session_factory, fake_agents):
    fake_agents["developer"].side_effect = RuntimeError("LLM down")
    run_id = await _run_plan(session_factory, fake_agents, ["tester", "developer", "self_evolve"])

    run = await get_run(session_factory, run_id)
    assert run.status == "failed"
    assert run.next_stage_index == 1  # the UI marks the developer stage as failed


@pytest.mark.asyncio
async def test_planner_saves_task_priorities(session_factory, monkeypatch):
    reply = '{"tasks": [{"id": 1, "description": "Add endpoint", "priority": "High"}]}'
    monkeypatch.setattr(planner_agent, "_ask_llm", lambda description: reply)
    project_id = (await get_run(session_factory, await new_run(session_factory))).project_id

    async with session_factory() as db:
        plan = await planner_agent.run(db, project_id, "add an endpoint")
        task = (await db.execute(select(Task))).scalar_one()

    assert plan.tasks[0].id == "1"
    assert task.priority == "high"


@pytest.mark.asyncio
async def test_planner_raises_on_a_bad_reply(session_factory, monkeypatch):
    monkeypatch.setattr(planner_agent, "_ask_llm", lambda description: "I think you should build it.")
    async with session_factory() as db:
        with pytest.raises(ValueError):
            await planner_agent.run(db, 1, "add an endpoint")
