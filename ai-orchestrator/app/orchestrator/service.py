"""Runs the agent pipeline for one request.

How a run works:
  1. The Overseer picks the stages (planner, designer, developer, ...) and
     the points where a human should check the work ("checkpoints").
  2. Stages run one after another.
  3. At a checkpoint the run stops with status "awaiting_human" and saves
     which stage comes next (`next_stage_index`).
  4. When the human answers, the run starts again from that stage.

Inside the stages:
  - Developer and Critic go back and forth until the code scores well
    enough (DEBATE_MAX_ROUNDS, DEBATE_SCORE_THRESHOLD).
  - If tests fail, the Developer fixes the code and the tests run again
    (RECOVERY_MAX_ATTEMPTS).
  - Instructions learned from past runs (evolved prompts) are added to
    each agent's prompt.

Everything is saved in the database, so nothing is kept in memory
between a pause and a resume.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.critic import critic_agent
from app.agents.designer import designer_agent
from app.agents.developer import developer_agent
from app.agents.overseer import overseer_agent
from app.agents.persona import persona_context
from app.agents.planner import planner_agent
from app.agents.self_evolve import self_evolve_agent
from app.agents.sub_agent_spawner import sub_agent_spawner
from app.agents.tester import tester_agent
from app.config import settings
from app.db import AsyncSessionLocal
from app.memory.agent_bus import AgentBus
from app.memory.evolved_prompts import load_evolved_prompts
from app.memory.vector_store import vector_store
from app.models.core import AgentExecution, ConversationLog, PipelineRun, Project, utc_now
from app.schemas.core import (
    DesignOutput,
    PlannerOutput,
    PlannerTaskItem,
    TestResult,
)
from app.utils.logging import log_structured

T = TypeVar("T")


class OrchestrationError(Exception):
    """Raised when orchestration fails for an agent stage."""

    def __init__(self, agent_name: str, message: str) -> None:
        super().__init__(message)
        self.agent_name = agent_name
        self.message = message


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _ensure_project(db: AsyncSession, project_id: int) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise OrchestrationError("orchestrator", f"Project {project_id} not found.")
    return project


async def _log_conversation(db: AsyncSession, project_id: int, role: str, content: str) -> None:
    log = ConversationLog(project_id=project_id, role=role, content=content)
    db.add(log)
    await db.commit()


async def _start_execution(
    db: AsyncSession, project_id: int, run_id: int, agent_name: str, input_payload: dict | None
) -> AgentExecution:
    execution = AgentExecution(
        project_id=project_id,
        pipeline_run_id=run_id,
        agent_name=agent_name,
        input_payload=input_payload,
        status="running",
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return execution


async def _complete_execution(
    db: AsyncSession,
    execution_id: int,
    status: str,
    output_payload: dict | None,
    execution_time: float = 0.0,
    tokens_used: int = 0,
    error_message: str = "",
) -> None:
    await db.execute(
        update(AgentExecution)
        .where(AgentExecution.id == execution_id)
        .values(
            status=status,
            output_payload=output_payload,
            execution_time=execution_time,
            tokens_used=tokens_used,
            error_message=error_message,
        )
    )
    await db.commit()


async def _run_with_retries(agent_name: str, func, *args: Any, **kwargs: Any) -> Any:
    """Call an agent, trying again if it raises.

    There is no extra timeout here on purpose. The agent runs in a thread,
    and a thread cannot be stopped from outside, so a timeout here would
    only stop waiting while the LLM call kept going in the background.
    Each LLM call already has its own network timeout (see services/llm.py).
    """
    last_error = "Unknown error"
    for attempt in range(1, settings.AGENT_MAX_RETRIES + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            last_error = str(exc)
            log_structured("agent_retry_error", agent=agent_name, attempt=attempt, error=last_error)
    raise OrchestrationError(agent_name, last_error)


async def _build_context(project_id: int, description: str) -> str:
    """Retrieve vector memory context and build a context string."""
    results = await vector_store.query(project_id=project_id, query_text=description, top_k=5)
    if not results:
        return ""
    snippets = [doc for doc, _meta in results]
    return "\n\n".join(snippets)


async def _update_pipeline_run(db: AsyncSession, run_id: int, **kwargs: Any) -> None:
    await db.execute(update(PipelineRun).where(PipelineRun.id == run_id).values(**kwargs))
    await db.commit()


def _build_evolved_prefix(agent_name: str, evolved_dict: dict) -> str:
    """Build a prefix string from evolved instructions for a specific agent."""
    instructions = evolved_dict.get(agent_name, [])
    if not instructions:
        return ""
    return (
        f"[Evolved {agent_name} instructions from {len(instructions)} past run(s)]:\n"
        + "\n".join(f"  • {instr}" for instr in instructions[-5:])
        + "\n\n"
    )


async def _build_full_description(
    project_id: int,
    feature_description: str,
    persona: str,
    extra_heading: str,
    extra_text: str | None,
) -> str:
    """The request text every agent sees: style hint + request + memory + human notes."""
    parts = [f"[Output style: {persona_context(persona)}]", feature_description]
    context = await _build_context(project_id, feature_description)
    if context:
        parts.append(f"Context from project memory:\n{context}")
    if extra_text:
        parts.append(f"{extra_heading}:\n{extra_text}")
    return "\n\n".join(parts)


def _tasks_or_default(raw_tasks: list[dict] | None, feature_description: str) -> PlannerOutput:
    """Saved planner tasks, or one task covering the whole request if the planner did not run."""
    if raw_tasks:
        return PlannerOutput(tasks=[PlannerTaskItem(**task) for task in raw_tasks])
    return PlannerOutput(tasks=[PlannerTaskItem(id="t1", description=feature_description, priority="medium")])


# ---------------------------------------------------------------------------
# Stage runner helpers
# ---------------------------------------------------------------------------

async def _run_tracked(
    db: AsyncSession,
    project_id: int,
    run_id: int,
    agent_name: str,
    input_payload: dict,
    work: Awaitable[T],
    describe: Callable[[T], dict],
) -> tuple[T, float]:
    """Await one agent call and save it as an AgentExecution row.

    The row stores how long the call took and whether it failed. The
    Analytics page counts these rows. Returns (result, seconds).
    Errors are saved and then raised again.
    """
    record = await _start_execution(db, project_id, run_id, agent_name, input_payload)
    start = time.time()
    try:
        result = await work
    except Exception as exc:
        await _complete_execution(db, record.id, "failed", {"error": str(exc)},
                                  execution_time=time.time() - start, error_message=str(exc))
        raise
    seconds = time.time() - start
    await _complete_execution(db, record.id, "completed", describe(result), execution_time=seconds)
    return result, seconds


def _describe_review(review: dict) -> dict:
    return {"score": review["score"], "critique": review["critique"]}


def _describe_code(code: str) -> dict:
    return {"generated_code": code}


def _design_text(design: DesignOutput) -> str:
    return (
        f"Architecture: {design.architecture}\n"
        f"Components: {', '.join(design.components)}\n"
        f"API Contracts: {design.api_contracts}"
    )


async def _run_planner(
    db: AsyncSession,
    run_id: int,
    project_id: int,
    full_description: str,
    feature_description: str,
    timeline: list,
) -> PlannerOutput:
    """Run the planner and save its tasks. Marks the run failed and raises if it fails."""
    await _update_pipeline_run(db, run_id, status="planning", current_agent="planner")
    await _log_conversation(db, project_id, "user", feature_description)
    try:
        plan, seconds = await _run_tracked(
            db, project_id, run_id, "planner", {"description": feature_description},
            _run_with_retries("planner", planner_agent.run, db, project_id, full_description),
            lambda plan: plan.model_dump(),
        )
    except Exception as exc:
        timeline.append({"agent": "planner", "status": "failed", "error": str(exc)})
        await _update_pipeline_run(db, run_id, status="failed", error_message=f"Planner failed: {exc}",
                                   current_agent="", execution_timeline=timeline)
        raise
    timeline.append({"agent": "planner", "status": "completed", "time": round(seconds, 2)})
    await _update_pipeline_run(db, run_id, planned_tasks=[t.model_dump() for t in plan.tasks],
                               execution_timeline=timeline)
    return plan


async def _run_designer(
    db: AsyncSession,
    run_id: int,
    project_id: int,
    full_description: str,
    feature_description: str,
    planned_tasks: PlannerOutput,
    timeline: list,
) -> None:
    """Run the designer and save its design. A failure here does not stop the run."""
    await _update_pipeline_run(db, run_id, status="designing", current_agent="designer")
    try:
        design, seconds = await _run_tracked(
            db, project_id, run_id, "designer", {"description": feature_description},
            designer_agent.run(full_description, planned_tasks),
            lambda design: design.model_dump(),
        )
    except Exception as exc:
        timeline.append({"agent": "designer", "status": "failed", "error": str(exc)})
        await _update_pipeline_run(db, run_id, execution_timeline=timeline)
        log_structured("designer_failed", run_id=run_id, error=str(exc))
        return
    timeline.append({"agent": "designer", "status": "completed", "time": round(seconds, 2)})
    await _update_pipeline_run(db, run_id, design_artifact=_design_text(design), execution_timeline=timeline)


# ---------------------------------------------------------------------------
# Developer <-> Critic debate, extra critic pass, and test-and-fix loop
# ---------------------------------------------------------------------------

def _code_already_reviewed(timeline: list[dict]) -> bool:
    """True if the critic already scored the current code in the debate loop.

    We look at the last entry where code was written or reviewed. If that
    is a debate round, the code has not changed since the critic saw it,
    so another critic pass would only repeat the same review.
    """
    for entry in reversed(timeline):
        if entry.get("agent") in ("developer", "critic"):
            return entry.get("type") == "debate_round"
    return False


async def _run_debate_loop(
    db: AsyncSession,
    run_id: int,
    project_id: int,
    full_description: str,
    feature_description: str,
    planned_tasks: PlannerOutput,
    timeline: list,
    evolved_dict: dict,
    bus: AgentBus | None = None,
) -> tuple[str, int]:
    """The developer writes code, then the critic and developer take turns.

    Stops when the score reaches DEBATE_SCORE_THRESHOLD, or after
    DEBATE_MAX_ROUNDS reviews. Returns (code, last score).
    Raises if the first version of the code cannot be written.
    """
    learned = evolved_dict.get("developer") or None

    await _update_pipeline_run(db, run_id, status="developing", current_agent="developer")
    try:
        code, seconds = await _run_tracked(
            db, project_id, run_id, "developer", {"description": feature_description},
            _run_with_retries("developer", developer_agent.run, full_description, planned_tasks),
            _describe_code,
        )
    except Exception as exc:
        timeline.append({"agent": "developer", "status": "failed", "error": str(exc)})
        await _update_pipeline_run(db, run_id, status="failed", error_message=f"Developer failed: {exc}",
                                   current_agent="", execution_timeline=timeline)
        raise
    timeline.append({"agent": "developer", "status": "completed", "type": "initial", "time": round(seconds, 2)})
    await _update_pipeline_run(db, run_id, generated_code=code, execution_timeline=timeline)

    score = 0
    for round_num in range(1, settings.DEBATE_MAX_ROUNDS + 1):
        await _update_pipeline_run(db, run_id, status=f"debating_round_{round_num}",
                                   current_agent=f"critic(debate_r{round_num})")
        try:
            review, seconds = await _run_tracked(
                db, project_id, run_id, "critic", {"phase": "debate", "round": round_num},
                critic_agent.critique_code(code, bus=bus), _describe_review,
            )
        except Exception as exc:
            log_structured("debate_critic_failed", run_id=run_id, round=round_num, error=str(exc))
            break

        score = review["score"]
        done = score >= settings.DEBATE_SCORE_THRESHOLD or round_num == settings.DEBATE_MAX_ROUNDS
        if done and review["improved"] != code:
            # Out of rounds and still below the bar: use the critic's own
            # rewrite. The critic has already checked that it is valid Python.
            code = review["improved"]
            await _update_pipeline_run(db, run_id, generated_code=code)

        timeline.append({
            "agent": "critic",
            "status": "completed",
            "type": "debate_round",
            "round": round_num,
            "score": score,
            "critique": review["critique"][:400],
            "action": "pass" if done else "revise",
            "time": round(seconds, 2),
        })
        await _update_pipeline_run(db, run_id, execution_timeline=timeline)
        log_structured("debate_round", run_id=run_id, round=round_num, score=score, done=done)
        if done:
            break

        await _update_pipeline_run(db, run_id, current_agent=f"developer(revision_r{round_num})")
        try:
            code, seconds = await _run_tracked(
                db, project_id, run_id, "developer", {"phase": "revision", "round": round_num},
                developer_agent.revise(code, review["critique"], feature_description, learned, bus=bus),
                _describe_code,
            )
        except Exception as exc:
            log_structured("debate_revision_failed", run_id=run_id, round=round_num, error=str(exc))
            break  # Keep the last good code.
        timeline.append({"agent": "developer", "status": "completed", "type": "revision",
                         "round": round_num, "time": round(seconds, 2)})
        await _update_pipeline_run(db, run_id, generated_code=code, execution_timeline=timeline)

    log_structured("debate_complete", run_id=run_id, final_score=score)
    return code, score


async def _run_critic(
    db: AsyncSession,
    run_id: int,
    project_id: int,
    code: str,
    timeline: list,
) -> str:
    """One extra review by the critic. Never fails the run. Returns the (maybe improved) code."""
    await _update_pipeline_run(db, run_id, status="critiquing_code", current_agent="critic")
    try:
        review, seconds = await _run_tracked(
            db, project_id, run_id, "critic", {"phase": "code_review"},
            critic_agent.critique_code(code), _describe_review,
        )
    except Exception as exc:
        timeline.append({"agent": "critic", "status": "skipped", "error": str(exc)})
        await _update_pipeline_run(db, run_id, execution_timeline=timeline)
        log_structured("critic_skipped", run_id=run_id, error=str(exc))
        return code

    timeline.append({"agent": "critic", "status": "completed", "score": review["score"], "time": round(seconds, 2)})
    await _update_pipeline_run(db, run_id, generated_code=review["improved"], execution_timeline=timeline)
    return review["improved"]


async def _run_tester_with_recovery(
    db: AsyncSession,
    run_id: int,
    project_id: int,
    code: str,
    full_description: str,
    feature_description: str,
    timeline: list,
    evolved_dict: dict,
) -> tuple[TestResult, str]:
    """Run the tests. If they fail, the developer fixes the code and we test again.

    Tries up to RECOVERY_MAX_ATTEMPTS times. Returns (test result, final code).
    The test code is saved on the run after every attempt.
    """
    learned = evolved_dict.get("developer") or None
    result = TestResult(status="fail", coverage=0.0, errors="Tester did not run.")

    for attempt in range(1, settings.RECOVERY_MAX_ATTEMPTS + 1):
        agent_name = "tester" if attempt == 1 else f"tester(retry_{attempt})"
        await _update_pipeline_run(db, run_id, status="testing", current_agent=agent_name)
        start = time.time()
        try:
            (result, tests), seconds = await _run_tracked(
                db, project_id, run_id, agent_name, {"description": feature_description, "attempt": attempt},
                _run_with_retries("tester", tester_agent.run, code, full_description),
                lambda output: output[0].model_dump(),
            )
            await _update_pipeline_run(db, run_id, test_code=tests)
            entry = {"agent": "tester", "status": "completed" if result.status == "pass" else "failed",
                     "time": round(seconds, 2)}
        except Exception as exc:
            result = TestResult(status="fail", coverage=0.0, errors=str(exc))
            entry = {"agent": "tester", "status": "failed", "time": round(time.time() - start, 2),
                     "error": str(exc)[:300]}
        if attempt > 1:
            entry.update(type="test_attempt", attempt=attempt)
        timeline.append(entry)
        await _update_pipeline_run(db, run_id, execution_timeline=timeline)

        if result.status == "pass":
            log_structured("recovery_success", run_id=run_id, attempt=attempt)
            break
        if attempt == settings.RECOVERY_MAX_ATTEMPTS:
            log_structured("recovery_exhausted", run_id=run_id, attempts=attempt)
            break

        errors = (result.errors or "Unknown test errors")[:1200]
        log_structured("recovery_attempt", run_id=run_id, attempt=attempt, errors_preview=errors[:100])
        await _update_pipeline_run(db, run_id, status=f"recovering_attempt_{attempt}",
                                   current_agent=f"developer(recovery_{attempt})")
        feedback = (
            f"ATTEMPT {attempt} TEST FAILURES — fix ALL of these errors:\n\n{errors}\n\n"
            "IMPORTANT: Return the COMPLETE fixed Python module (not just the changed parts). "
            "Ensure all imports are correct, all referenced names are defined, "
            "and the module can be imported standalone without errors."
        )
        try:
            code, seconds = await _run_tracked(
                db, project_id, run_id, "developer", {"phase": "recovery", "attempt": attempt},
                developer_agent.revise(code, feedback, feature_description, learned),
                _describe_code,
            )
        except Exception as exc:
            log_structured("recovery_revision_failed", run_id=run_id, attempt=attempt, error=str(exc))
            break  # Keep the last good code.
        timeline.append({"agent": "developer", "status": "completed", "type": "recovery",
                         "attempt": attempt, "time": round(seconds, 2)})
        await _update_pipeline_run(db, run_id, generated_code=code, execution_timeline=timeline)

    return result, code


async def _run_self_evolve(
    db: AsyncSession,
    run_id: int,
    project_id: int,
    feature_description: str,
    generated_code: str,
    test_status: str,
    timeline: list,
) -> None:
    """Let the self-evolve agent learn from this run. A failure here does not stop the run."""
    try:
        _, seconds = await _run_tracked(
            db, project_id, run_id, "self_evolve", {"test_status": test_status},
            self_evolve_agent.learn(project_id=project_id, feature_description=feature_description,
                                    generated_code=generated_code, test_status=test_status),
            lambda _: {"learned": True},
        )
        timeline.append({"agent": "self_evolve", "status": "learned", "time": round(seconds, 2)})
    except Exception as exc:
        timeline.append({"agent": "self_evolve", "status": "skipped", "error": str(exc)})
        log_structured("self_evolve_skipped", run_id=run_id, error=str(exc))
    await _update_pipeline_run(db, run_id, execution_timeline=timeline)


# ---------------------------------------------------------------------------
# Background pipeline execution — Overseer-gated
# ---------------------------------------------------------------------------

async def fail_interrupted_runs() -> int:
    """Mark runs that a server restart cut off as failed. Returns how many.

    Pipelines run as background tasks inside this process. If the server
    stops halfway, the run would show "developing" (or similar) forever.
    Runs waiting for a human are fine: they are paused in the database.
    This assumes one server process. With several workers, one worker
    starting up would fail runs that another worker is still running.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(PipelineRun)
            .where(PipelineRun.status.not_in(("completed", "failed", "awaiting_human")))
            .values(status="failed", current_agent="", error_message="Stopped because the server restarted.")
        )
        # A stage re-run that was cut off leaves current_agent set, which would
        # block the run forever. Nothing is running at startup, so clear it.
        await db.execute(update(PipelineRun).where(PipelineRun.current_agent != "").values(current_agent=""))
        await db.commit()
    return result.rowcount


def _sub_agents_wrote_code(timeline: list[dict]) -> bool:
    """True if the sub-agent spawner already wrote this run's code.

    Read from the saved timeline, so the answer survives a checkpoint pause.
    """
    events = {entry.get("event") for entry in timeline if entry.get("type") == "sub_agent_spawn"}
    return "spawn_decision" in events and "spawn_fallback" not in events


async def run_pipeline_background(run_id: int, project_id: int, human_input: str | None = None) -> None:
    """Run the plan's stages in order, pausing at checkpoints.

    This is called once when a run starts, and again each time a human
    answers a checkpoint. `run.next_stage_index` is the first stage that
    has not finished yet, so a resume starts there.
    We save the position as a number, not a stage name, because a plan can
    list the same stage twice (the bug flow runs the tester before and after the fix).
    """
    async with AsyncSessionLocal() as db:
        try:
            run = await db.get(PipelineRun, run_id)
            if run is None:
                return
            await _ensure_project(db, project_id)

            feature_description = run.feature_description
            bus = AgentBus(project_id=project_id, run_id=run_id, log_dir=settings.CHROMA_DIR)
            evolved_dict = await asyncio.to_thread(load_evolved_prompts, project_id)
            full_description = await _build_full_description(
                project_id, feature_description, run.persona or "intermediate", "Human guidance", human_input
            )

            plan = run.overseer_plan
            if not plan:
                await _update_pipeline_run(db, run_id, status="planning_overseer", current_agent="overseer")
                plan = await overseer_agent.plan(feature_description, run.request_type)
                await _update_pipeline_run(db, run_id, overseer_plan=plan)
                log_structured("overseer_plan", run_id=run_id, plan=plan)

            stages: list[str] = plan.get("stages", [])
            checkpoints: list[str] = plan.get("checkpoints", [])
            start_index = run.next_stage_index or 0

            # Load what earlier stages already produced. They may have run before a pause.
            timeline: list[dict] = list(run.execution_timeline or [])
            planned_tasks = _tasks_or_default(run.planned_tasks, feature_description)
            generated_code = run.generated_code or ""
            final_test_result = TestResult(**run.test_result) if run.test_result else None
            sub_agents_wrote_code = _sub_agents_wrote_code(timeline)

            await _update_pipeline_run(db, run_id, checkpoint_stage=None, checkpoint_prompt=None)

            for index in range(start_index, len(stages)):
                stage = stages[index]
                # Saved before the stage starts, so the UI can show which stage is running.
                await _update_pipeline_run(db, run_id, next_stage_index=index)

                if stage == "planner":
                    try:
                        planned_tasks = await _run_planner(
                            db, run_id, project_id,
                            _build_evolved_prefix("planner", evolved_dict) + full_description,
                            feature_description, timeline,
                        )
                    except Exception:
                        return  # _run_planner already marked the run as failed

                    # If the plan needs several specialists, sub-agents write the code now.
                    spawner_result = await sub_agent_spawner.analyse_and_spawn(
                        project_id=project_id,
                        feature_description=feature_description,
                        planned_tasks=[{"description": task.description} for task in planned_tasks.tasks],
                        timeline=timeline,
                        evolved_instructions=_build_evolved_prefix("developer", evolved_dict),
                        bus=bus,
                    )
                    if spawner_result.was_triggered and spawner_result.composed_code:
                        log_structured("sub_agent_spawn_used", run_id=run_id,
                                       agents=len(spawner_result.spawned_agents))
                        generated_code = spawner_result.composed_code
                        sub_agents_wrote_code = True
                        await _update_pipeline_run(
                            db, run_id, generated_code=generated_code, execution_timeline=timeline
                        )

                elif stage == "designer":
                    await _run_designer(
                        db, run_id, project_id,
                        _build_evolved_prefix("designer", evolved_dict) + full_description,
                        feature_description, planned_tasks, timeline,
                    )

                elif stage == "developer":
                    if sub_agents_wrote_code:
                        # The sub-agents already wrote the code, so we skip the debate loop.
                        log_structured("developer_stage_skipped", run_id=run_id, reason="sub_agents_produced_code")
                        timeline.append({
                            "agent": "developer",
                            "event": "skipped",
                            "reason": "Sub-agent spawning produced composed code — debate loop skipped",
                        })
                    else:
                        try:
                            generated_code, _final_score = await _run_debate_loop(
                                db, run_id, project_id,
                                _build_evolved_prefix("developer", evolved_dict) + full_description,
                                feature_description, planned_tasks, timeline, evolved_dict, bus=bus,
                            )
                        except Exception:
                            return  # _run_debate_loop already marked the run as failed

                elif stage == "critic":
                    if not generated_code:
                        timeline.append({"agent": "critic", "status": "skipped", "reason": "No code to review yet."})
                    elif _code_already_reviewed(timeline):
                        timeline.append({"agent": "critic", "status": "skipped",
                                         "reason": "Code was already reviewed in the debate loop."})
                    else:
                        generated_code = await _run_critic(db, run_id, project_id, generated_code, timeline)

                elif stage == "tester":
                    if not generated_code:
                        timeline.append({"agent": "tester", "status": "skipped", "reason": "No code to test yet."})
                    else:
                        final_test_result, generated_code = await _run_tester_with_recovery(
                            db, run_id, project_id, generated_code,
                            _build_evolved_prefix("tester", evolved_dict) + full_description,
                            feature_description, timeline, evolved_dict,
                        )
                        # Save now, so the result is not lost if the run pauses after this stage.
                        await _update_pipeline_run(
                            db, run_id, generated_code=generated_code, test_result=final_test_result.model_dump()
                        )

                elif stage == "self_evolve":
                    if generated_code:
                        test_status = final_test_result.status if final_test_result else "unknown"
                        await _run_self_evolve(
                            db, run_id, project_id, feature_description, generated_code, test_status, timeline
                        )

                checkpoint = f"after_{stage}"
                if checkpoint in checkpoints:
                    await _update_pipeline_run(
                        db, run_id,
                        status="awaiting_human",
                        current_agent="",
                        checkpoint_stage=checkpoint,
                        checkpoint_prompt=_build_checkpoint_prompt(
                            stage, planned_tasks, generated_code, final_test_result
                        ),
                        next_stage_index=index + 1,
                        execution_timeline=timeline,
                    )
                    log_structured("pipeline_checkpoint", run_id=run_id, stage=checkpoint, next_index=index + 1)
                    return  # Paused. The checkpoint endpoint starts us again.

            # ---- All stages done ----
            bus_summary = bus.summary()
            if bus_summary["total_messages"] > 0:
                timeline.append({"type": "p2p_bus_summary", **bus_summary})

            if generated_code:
                await vector_store.add_documents(
                    project_id=project_id,
                    documents=[
                        f"Feature description:\n{feature_description}",
                        f"Generated code:\n{generated_code}",
                    ],
                    metadatas=[{"type": "feature"}, {"type": "code"}],
                )

            await _update_pipeline_run(
                db, run_id,
                status="completed",
                current_agent="",
                next_stage_index=len(stages),
                generated_code=generated_code,
                test_result=final_test_result.model_dump() if final_test_result else {},
                execution_timeline=timeline,
                completed_at=utc_now(),
            )
            log_structured("pipeline_completed", run_id=run_id, project_id=project_id)

        except Exception as exc:
            log_structured("pipeline_fatal_error", run_id=run_id, error=str(exc))
            try:
                await _update_pipeline_run(db, run_id, status="failed", error_message=str(exc), current_agent="")
            except Exception:
                pass


def _build_checkpoint_prompt(
    stage: str,
    planned_tasks: PlannerOutput | None,
    generated_code: str,
    test_result: TestResult | None,
) -> str:
    """Build a descriptive checkpoint message for the human reviewer."""
    if stage == "planner":
        task_count = len(planned_tasks.tasks) if planned_tasks else 0
        tasks_preview = ""
        if planned_tasks:
            tasks_preview = "\n".join(
                f"  • [{t.priority}] {t.description}" for t in planned_tasks.tasks[:5]
            )
        return (
            f"The Planner has broken the request into {task_count} task(s):\n{tasks_preview}\n\n"
            "Approve to continue to design/development, or provide modified instructions."
        )
    elif stage == "designer":
        return (
            "The Designer has produced the architecture and API contracts.\n"
            "Review the design artifact on the right.\n\n"
            "Approve to start development, or provide corrections."
        )
    elif stage == "developer":
        lines = len(generated_code.splitlines()) if generated_code else 0
        return (
            f"The Developer has written {lines} line(s) of code "
            f"(after debate loop refinement).\n"
            "Review the generated code on the right.\n\n"
            "Approve to run tests, or provide modification instructions."
        )
    elif stage == "critic":
        return (
            "The Critic has reviewed the code and applied improvements.\n\n"
            "Approve to proceed to testing, or provide additional review criteria."
        )
    elif stage == "tester":
        status = test_result.status if test_result else "unknown"
        coverage = test_result.coverage if test_result else 0
        return (
            f"Tests completed: status={status}, coverage={coverage}%.\n\n"
            "Approve to finalise the pipeline, or request additional test cases."
        )
    return f"Stage '{stage}' has completed. Approve to continue."


# ---------------------------------------------------------------------------
# Stage retrigger (for team collaboration / non-linear flow)
# ---------------------------------------------------------------------------

# Which agent each team stage re-runs.
_RETRIGGER_AGENTS = {"planning": "planner", "designing": "designer", "developing": "developer", "testing": "tester"}


async def retrigger_stage_background(
    run_id: int,
    project_id: int,
    stage: str,
    team_content: str | None = None,
) -> None:
    """Re-run one stage of a finished or paused run, using a team member's input.

    The route set `current_agent` to claim the run before starting this.
    We always clear it at the end, even if the stage fails, so the run
    does not stay locked.
    """
    agent = _RETRIGGER_AGENTS[stage]
    async with AsyncSessionLocal() as db:
        try:
            run = await db.get(PipelineRun, run_id)
            if run is None:
                return
            evolved_dict = await asyncio.to_thread(load_evolved_prompts, project_id)
            description = _build_evolved_prefix(agent, evolved_dict) + await _build_full_description(
                project_id, run.feature_description, run.persona or "intermediate", "Team input / override",
                team_content,
            )
            tasks = _tasks_or_default(run.planned_tasks, run.feature_description)
            timeline = list(run.execution_timeline or [])
            tracked = (db, project_id, run_id, f"{agent}(retrigger)", {"team_content": team_content})

            changes: dict[str, Any] = {}
            try:
                if stage == "planning":
                    plan, seconds = await _run_tracked(
                        *tracked, _run_with_retries("planner", planner_agent.run, db, project_id, description),
                        lambda plan: plan.model_dump(),
                    )
                    changes["planned_tasks"] = [t.model_dump() for t in plan.tasks]
                elif stage == "designing":
                    design, seconds = await _run_tracked(
                        *tracked, designer_agent.run(description, tasks), lambda design: design.model_dump()
                    )
                    text = _design_text(design)
                    changes["design_artifact"] = f"[Team override applied]\n{text}" if team_content else text
                elif stage == "developing":
                    code, seconds = await _run_tracked(
                        *tracked, _run_with_retries("developer", developer_agent.run, description, tasks),
                        _describe_code,
                    )
                    changes["generated_code"] = code
                else:  # testing
                    if not run.generated_code:
                        raise ValueError("There is no code to test yet.")
                    if team_content:
                        description += f"\n\nAdditional test cases from QA:\n{team_content}"
                    (result, tests), seconds = await _run_tracked(
                        *tracked, _run_with_retries("tester", tester_agent.run, run.generated_code, description),
                        lambda output: output[0].model_dump(),
                    )
                    changes.update(test_result=result.model_dump(), test_code=tests)
                timeline.append({"agent": f"{agent}(team)", "status": "completed", "time": round(seconds, 2)})
            except Exception as exc:
                timeline.append({"agent": f"{agent}(team)", "status": "failed", "error": str(exc)})

            await _update_pipeline_run(db, run_id, execution_timeline=timeline, **changes)
            log_structured("retrigger_completed", run_id=run_id, stage=stage, success=bool(changes))
        except Exception as exc:
            log_structured("retrigger_fatal_error", run_id=run_id, stage=stage, error=str(exc))
        finally:
            try:
                await _update_pipeline_run(db, run_id, current_agent="")
            except Exception as exc:
                log_structured("retrigger_unlock_failed", run_id=run_id, error=str(exc))
