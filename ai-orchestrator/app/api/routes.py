"""FastAPI API routes for the AI Orchestrator.

Endpoints:
    POST /project                           – Create a new project
    GET  /projects                          – List all projects
    DELETE /project/{id}                    – Delete a project
    POST /project/{id}/persona              – Set user persona for a project
    POST /project/{id}/feature              – Start a feature/bug pipeline (background)
    GET  /project/{id}/pipeline             – List all pipeline runs for a project
    GET  /project/{id}/pipeline/{run_id}    – Poll pipeline status (progressive updates)
    GET  /project/{id}/executions           – List agent execution history (?run_id= for one run)
    GET  /project/{id}/tasks                – List all tasks for a project
    PATCH /project/{id}/tasks/{task_id}     – Update task status
    GET  /project/{id}/analytics            – Aggregated analytics for a project
    GET  /project/{id}/memory               – List ChromaDB memory entries for a project
    GET  /health                            – Health check
"""

from __future__ import annotations

import asyncio
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.sub_agent_spawner import SPECIALIST_ROLES
from app.config import settings
from app.db import get_db
from app.memory.agent_bus import load_bus_messages
from app.memory.dynamic_roles import load_dynamic_roles
from app.memory.evolved_prompts import load_evolved_prompts
from app.memory.vector_store import vector_store
from app.models.core import AgentExecution, PipelineRun, Project, Task, TeamInput
from app.orchestrator.service import retrigger_stage_background, run_pipeline_background
from app.schemas.core import (
    ROLE_STAGE_MAP,
    AgentExecutionRead,
    AgentStat,
    AnalyticsResponse,
    CheckpointResponse,
    FeatureRequest,
    MemoryEntry,
    PersonaSet,
    PipelineRunListItem,
    PipelineRunRead,
    PipelineStartResponse,
    ProjectCreate,
    ProjectRead,
    RetriggerResponse,
    TaskRead,
    TaskUpdate,
    TeamInputCreate,
    TeamInputRead,
)
from app.utils.execution import start_background

router = APIRouter()


async def _get_project_or_404(db: AsyncSession, project_id: int) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    """Health check endpoint."""
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    vector_status = "healthy" if vector_store.health_check() else "unhealthy"

    return {
        "status": "ok" if db_status == "healthy" else "degraded",
        "database": db_status,
        "vector_store": vector_status,
    }


# ---------------------------------------------------------------------------
# Project management
# ---------------------------------------------------------------------------


@router.post(
    "/project",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    """Create a new project."""
    project = Project(name=payload.name, description=payload.description)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ProjectRead.model_validate(project)


@router.get(
    "/projects",
    response_model=List[ProjectRead],
)
async def list_projects(db: AsyncSession = Depends(get_db)) -> List[ProjectRead]:
    """List all projects ordered by most recently created."""
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = list(result.scalars().all())
    return [ProjectRead.model_validate(p) for p in projects]


@router.delete(
    "/project/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a project and all its associated data."""
    project = await _get_project_or_404(db, project_id)
    await db.delete(project)
    await db.commit()


@router.post(
    "/project/{project_id}/persona",
    response_model=ProjectRead,
)
async def set_persona(
    project_id: int,
    payload: PersonaSet,
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    """Set the user persona for a project (simple / intermediate / expert)."""
    project = await _get_project_or_404(db, project_id)
    project.persona = payload.persona
    await db.commit()
    await db.refresh(project)
    return ProjectRead.model_validate(project)


# ---------------------------------------------------------------------------
# Feature / Bug pipeline (background execution with polling)
# ---------------------------------------------------------------------------


@router.post(
    "/project/{project_id}/feature",
    response_model=PipelineStartResponse,
)
async def submit_feature(
    project_id: int,
    payload: FeatureRequest,
    db: AsyncSession = Depends(get_db),
) -> PipelineStartResponse:
    """Submit a feature or bug request.

    Creates a PipelineRun record and starts the agent pipeline as a background
    task.  Returns immediately with a run_id so the frontend can poll for
    progressive updates via GET /project/{id}/pipeline/{run_id}.
    """
    # Verify project exists
    project = await _get_project_or_404(db, project_id)

    # Use project persona if not explicitly overridden
    persona = payload.persona or project.persona or "intermediate"

    # Create pipeline run record
    run = PipelineRun(
        project_id=project_id,
        feature_description=payload.description,
        request_type=payload.request_type,
        persona=persona,
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    start_background(run_pipeline_background(run.id, project_id), name=f"pipeline-run-{run.id}")

    return PipelineStartResponse(run_id=run.id, status="pending")


@router.get(
    "/project/{project_id}/pipeline",
    response_model=List[PipelineRunListItem],
)
async def list_pipeline_runs(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[PipelineRunListItem]:
    """List all pipeline runs for a project (history)."""
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.project_id == project_id)
        .order_by(PipelineRun.created_at.desc())
    )
    runs = list(result.scalars().all())
    return [PipelineRunListItem.model_validate(r) for r in runs]


@router.get(
    "/project/{project_id}/pipeline/{run_id}",
    response_model=PipelineRunRead,
)
async def get_pipeline_status(
    project_id: int,
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunRead:
    """Poll the current state of a pipeline run."""
    result = await db.execute(
        select(PipelineRun).where(
            PipelineRun.id == run_id,
            PipelineRun.project_id == project_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found.")
    return PipelineRunRead.model_validate(run)


# ---------------------------------------------------------------------------
# Execution history
# ---------------------------------------------------------------------------


@router.get(
    "/project/{project_id}/executions",
    response_model=List[AgentExecutionRead],
)
async def list_executions(
    project_id: int,
    run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> List[AgentExecutionRead]:
    """Agent executions for a project, oldest first. Pass `run_id` to get one run only."""
    await _get_project_or_404(db, project_id)

    query = select(AgentExecution).where(AgentExecution.project_id == project_id)
    if run_id is not None:
        query = query.where(AgentExecution.pipeline_run_id == run_id)
    result = await db.execute(query.order_by(AgentExecution.created_at.asc()))
    executions = list(result.scalars().all())
    return [AgentExecutionRead.model_validate(exe) for exe in executions]


# ---------------------------------------------------------------------------
# Task management
# ---------------------------------------------------------------------------


@router.get(
    "/project/{project_id}/tasks",
    response_model=List[TaskRead],
)
async def list_tasks(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[TaskRead]:
    """List all tasks for a project."""
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(Task)
        .where(Task.project_id == project_id)
        .order_by(Task.created_at.desc())
    )
    tasks = list(result.scalars().all())
    return [TaskRead.model_validate(t) for t in tasks]


@router.patch(
    "/project/{project_id}/tasks/{task_id}",
    response_model=TaskRead,
)
async def update_task_status(
    project_id: int,
    task_id: int,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
) -> TaskRead:
    """Update the status of a task."""
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.project_id == project_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    task.status = payload.status
    await db.commit()
    await db.refresh(task)
    return TaskRead.model_validate(task)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@router.get(
    "/project/{project_id}/analytics",
    response_model=AnalyticsResponse,
)
async def get_analytics(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> AnalyticsResponse:
    """Return aggregated analytics for a project."""
    await _get_project_or_404(db, project_id)

    # Pipeline run stats
    runs_result = await db.execute(
        select(PipelineRun).where(PipelineRun.project_id == project_id)
    )
    runs = list(runs_result.scalars().all())
    total_runs = len(runs)
    successful_runs = sum(1 for r in runs if r.status == "completed")
    failed_runs = sum(1 for r in runs if r.status == "failed")

    # Test pass rate
    completed_runs = [r for r in runs if r.status == "completed" and r.test_result]
    test_passes = sum(
        1 for r in completed_runs
        if isinstance(r.test_result, dict) and r.test_result.get("status") == "pass"
    )
    test_pass_rate = (test_passes / len(completed_runs) * 100) if completed_runs else 0.0

    # Task count
    tasks_result = await db.execute(
        select(func.count(Task.id)).where(Task.project_id == project_id)
    )
    total_tasks = tasks_result.scalar() or 0

    # Agent execution stats
    execs_result = await db.execute(
        select(AgentExecution).where(AgentExecution.project_id == project_id)
    )
    execs = list(execs_result.scalars().all())

    agent_map: dict[str, list[AgentExecution]] = {}
    for exe in execs:
        agent_map.setdefault(exe.agent_name, []).append(exe)

    agent_stats = []
    all_exec_times = []
    for agent_name, agent_execs in agent_map.items():
        times = [e.execution_time for e in agent_execs if e.execution_time > 0]
        all_exec_times.extend(times)
        agent_stats.append(
            AgentStat(
                agent_name=agent_name,
                total_runs=len(agent_execs),
                successful=sum(1 for e in agent_execs if e.status == "completed"),
                failed=sum(1 for e in agent_execs if e.status == "failed"),
                avg_execution_time=round(sum(times) / len(times), 2) if times else 0.0,
            )
        )

    avg_execution_time = round(sum(all_exec_times) / len(all_exec_times), 2) if all_exec_times else 0.0

    return AnalyticsResponse(
        total_runs=total_runs,
        successful_runs=successful_runs,
        failed_runs=failed_runs,
        total_tasks=total_tasks,
        avg_execution_time=avg_execution_time,
        test_pass_rate=round(test_pass_rate, 1),
        agent_stats=agent_stats,
    )


# ---------------------------------------------------------------------------
# Memory / Vector store
# ---------------------------------------------------------------------------


@router.get(
    "/project/{project_id}/memory",
    response_model=List[MemoryEntry],
)
async def list_memory(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[MemoryEntry]:
    """List all ChromaDB memory entries for a project."""
    await _get_project_or_404(db, project_id)

    entries = await vector_store.list_documents(project_id)
    return entries


# ---------------------------------------------------------------------------
# Human checkpoint — approve / modify / reject
# ---------------------------------------------------------------------------


async def _raise_run_busy(db: AsyncSession, project_id: int, run_id: int) -> None:
    """Raise 404 if the run does not exist, otherwise 409 saying what it is busy with."""
    run = await db.get(PipelineRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found.")
    busy_with = f", busy with: {run.current_agent}" if run.current_agent else ""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Pipeline cannot take this action right now (status: {run.status}{busy_with}).",
    )


@router.post(
    "/project/{project_id}/pipeline/{run_id}/checkpoint/respond",
    response_model=PipelineStartResponse,
)
async def respond_to_checkpoint(
    project_id: int,
    run_id: int,
    payload: CheckpointResponse,
    db: AsyncSession = Depends(get_db),
) -> PipelineStartResponse:
    """Human responds to a pipeline checkpoint.

    Actions:
      approve  – resume pipeline from the next stage with no extra input
      modify   – resume with human's instructions injected into the next stage
      reject   – abort the pipeline (status → failed)
    """
    # Check the status and change it in one statement. If two clicks arrive at
    # the same time, only one of them still matches, so the run can never be
    # resumed twice.
    rejected = payload.action == "reject"
    new_values = (
        {"status": "failed", "error_message": "Rejected by human reviewer.",
         "checkpoint_stage": None, "checkpoint_prompt": None, "next_stage_index": None}
        if rejected
        else {"status": "resuming"}
    )
    result = await db.execute(
        update(PipelineRun)
        .where(
            PipelineRun.id == run_id,
            PipelineRun.project_id == project_id,
            PipelineRun.status == "awaiting_human",
            PipelineRun.current_agent == "",  # no stage is being re-run right now
        )
        .values(**new_values)
    )
    await db.commit()
    if result.rowcount == 0:
        await _raise_run_busy(db, project_id, run_id)

    if rejected:
        return PipelineStartResponse(run_id=run_id, status="failed")

    human_input = payload.input if payload.action == "modify" else None
    start_background(
        run_pipeline_background(run_id, project_id, human_input=human_input),
        name=f"pipeline-run-{run_id}",
    )
    return PipelineStartResponse(run_id=run_id, status="resuming")


# ---------------------------------------------------------------------------
# Team collaboration — parallel input lanes
# ---------------------------------------------------------------------------


@router.post(
    "/project/{project_id}/pipeline/{run_id}/team-input",
    response_model=TeamInputRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_team_input(
    project_id: int,
    run_id: int,
    payload: TeamInputCreate,
    db: AsyncSession = Depends(get_db),
) -> TeamInputRead:
    """Submit a role-based input for a specific pipeline run stage.

    Each role maps to a stage:
      manager   → planning
      architect → designing
      developer → developing
      tester    → testing

    The input is stored and can be applied by calling the retrigger endpoint.
    """
    # Verify run exists and belongs to project
    result = await db.execute(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.project_id == project_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found.")

    stage = ROLE_STAGE_MAP.get(payload.role, "planning")

    team_input = TeamInput(
        project_id=project_id,
        pipeline_run_id=run_id,
        role=payload.role,
        stage=stage,
        content=payload.content,
        status="pending",
    )
    db.add(team_input)
    await db.commit()
    await db.refresh(team_input)
    return TeamInputRead.model_validate(team_input)


@router.get(
    "/project/{project_id}/pipeline/{run_id}/team-inputs",
    response_model=List[TeamInputRead],
)
async def list_team_inputs(
    project_id: int,
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[TeamInputRead]:
    """List all team inputs submitted for a pipeline run."""
    result = await db.execute(
        select(TeamInput)
        .where(TeamInput.pipeline_run_id == run_id, TeamInput.project_id == project_id)
        .order_by(TeamInput.created_at.desc())
    )
    inputs = list(result.scalars().all())
    return [TeamInputRead.model_validate(i) for i in inputs]


@router.post(
    "/project/{project_id}/pipeline/{run_id}/retrigger/{stage}",
    response_model=RetriggerResponse,
)
async def retrigger_stage(
    project_id: int,
    run_id: int,
    stage: str,
    db: AsyncSession = Depends(get_db),
) -> RetriggerResponse:
    """Re-trigger a specific pipeline stage using the latest pending team input for that stage.

    Stages: planning | designing | developing | testing
    The orchestrator re-runs only that stage, updates the pipeline run record,
    and marks the team input as applied.
    """
    if stage not in ["planning", "designing", "developing", "testing"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid stage. Must be: planning, designing, developing, testing")

    # Claim the run in one statement: it must be finished or paused, and no
    # other stage may be re-running. Otherwise two tasks would write to the
    # same run at once and one would overwrite the other's work.
    result = await db.execute(
        update(PipelineRun)
        .where(
            PipelineRun.id == run_id,
            PipelineRun.project_id == project_id,
            PipelineRun.status.in_(("completed", "failed", "awaiting_human")),
            PipelineRun.current_agent == "",
        )
        .values(current_agent=stage)
    )
    await db.commit()
    if result.rowcount == 0:
        await _raise_run_busy(db, project_id, run_id)

    # Find latest pending team input for this stage
    result = await db.execute(
        select(TeamInput)
        .where(
            TeamInput.pipeline_run_id == run_id,
            TeamInput.stage == stage,
            TeamInput.status == "pending",
        )
        .order_by(TeamInput.created_at.desc())
        .limit(1)
    )
    team_input = result.scalar_one_or_none()

    role = "auto"
    if team_input:
        role = team_input.role
        # Mark as applied
        team_input.status = "applied"
        await db.commit()

    # Fire background retrigger
    start_background(
        retrigger_stage_background(
            run_id=run_id,
            project_id=project_id,
            stage=stage,
            team_content=team_input.content if team_input else None,
        ),
        name=f"retrigger-{run_id}-{stage}",
    )

    return RetriggerResponse(
        message=f"Stage '{stage}' re-triggered in background.",
        stage=stage,
        role=role,
    )


# ---------------------------------------------------------------------------
# Evolved prompts — per-agent structural prompt evolution
# ---------------------------------------------------------------------------


@router.get(
    "/project/{project_id}/evolved-prompts",
)
async def get_evolved_prompts(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the evolved (structural) prompt instructions for each agent.

    These are written by the Self-Evolve agent after every run and are
    added to agent prompts on later runs.
    """
    await _get_project_or_404(db, project_id)

    prompts = await asyncio.to_thread(load_evolved_prompts, project_id)
    return {
        "project_id": project_id,
        "agents": prompts,
        "total_instructions": sum(len(v) for v in prompts.values()),
    }


@router.get(
    "/project/{project_id}/dynamic-roles",
)
async def get_dynamic_roles(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return static + runtime-discovered specialist roles.

    Static roles are the 6 hardcoded types. Dynamic roles are written by
    RoleDiscoveryAgent / SelfEvolveAgent at runtime into dynamic_roles.json.
    """
    await _get_project_or_404(db, project_id)

    dynamic = await asyncio.to_thread(load_dynamic_roles)

    static_roles = [
        {"name": name, "keywords": cfg.get("keywords", []), "label": cfg.get("label", name), "source": "static"}
        for name, cfg in SPECIALIST_ROLES.items()
    ]
    dynamic_roles = [
        {"name": name, "keywords": cfg.get("keywords", []), "label": cfg.get("label", name), "source": "dynamic"}
        for name, cfg in dynamic.items()
    ]
    return {
        "static_roles": static_roles,
        "dynamic_roles": dynamic_roles,
        "total_static": len(static_roles),
        "total_dynamic": len(dynamic_roles),
    }


@router.get(
    "/run/{run_id}/bus-messages",
)
async def get_bus_messages(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return P2P bus messages logged during a specific pipeline run.

    Messages are written to bus_run_{id}.json in the Chroma data directory
    by AgentBus._persist() on every send().
    """
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")

    messages = await asyncio.to_thread(load_bus_messages, settings.CHROMA_DIR, run_id)

    return {
        "run_id": run_id,
        "messages": messages,
        "total": len(messages),
    }


@router.get(
    "/project/{project_id}/level5",
)
async def get_level5_summary(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return aggregated Level 5 activity for a project.

    Aggregates across all pipeline runs:
      - Total debate rounds (Developer ↔ Critic)
      - Total P2P bus messages
      - Total sub-agents spawned
      - Total new roles discovered at runtime
      - Evolved prompt instructions per agent
      - Dynamic roles library

    Also returns per-run breakdown for the last 10 runs.
    """
    await _get_project_or_404(db, project_id)

    runs_result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.project_id == project_id)
        .order_by(PipelineRun.created_at.desc())
    )
    runs = list(runs_result.scalars().all())

    total_debate_rounds = 0
    total_bus_messages = 0
    total_spawned_agents = 0
    total_role_discoveries = 0
    recent_runs_info = []

    for run in runs[:20]:
        timeline = run.execution_timeline or []

        debate_rounds = [e for e in timeline if e.get("type") == "debate_round"]
        spawns = [e for e in timeline if e.get("type") == "sub_agent_result"]
        discoveries = [
            e for e in timeline if e.get("type") == "sub_agent_spawn" and e.get("event") == "new_role_discovered"
        ]
        bus_entry = next((e for e in timeline if e.get("type") == "p2p_bus_summary"), None)
        bus_count = bus_entry.get("total_messages", 0) if bus_entry else 0

        total_debate_rounds += len(debate_rounds)
        total_spawned_agents += len(spawns)
        total_role_discoveries += len(discoveries)
        total_bus_messages += bus_count

        recent_runs_info.append({
            "run_id": run.id,
            "status": run.status,
            "feature_description": (run.feature_description or "")[:80],
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "debate_rounds": len(debate_rounds),
            "debate_scores": [e.get("score") for e in debate_rounds],
            "spawned_agents": [
                {"role": e.get("role"), "label": e.get("label"), "success": e.get("success")} for e in spawns
            ],
            "role_discoveries": [{"role": e.get("role"), "label": e.get("label")} for e in discoveries],
            "bus_messages": bus_count,
            "bus_agents": bus_entry.get("agents_with_inbox", []) if bus_entry else [],
        })

    evolved = await asyncio.to_thread(load_evolved_prompts, project_id)
    dynamic_roles = await asyncio.to_thread(load_dynamic_roles)

    return {
        "project_id": project_id,
        "totals": {
            "debate_rounds": total_debate_rounds,
            "bus_messages": total_bus_messages,
            "spawned_agents": total_spawned_agents,
            "role_discoveries": total_role_discoveries,
            "evolved_instructions": sum(len(v) for v in evolved.values()),
            "dynamic_roles": len(dynamic_roles),
        },
        "evolved_prompts": {
            agent: instrs[-5:]
            for agent, instrs in evolved.items()
        },
        "dynamic_roles": [
            {"name": name, "label": cfg.get("label", name), "keywords": cfg.get("keywords", [])}
            for name, cfg in dynamic_roles.items()
        ],
        "recent_runs": recent_runs_info,
    }


@router.get(
    "/run/{run_id}/sub-agents",
)
async def get_sub_agent_spawns(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return sub-agent spawn events from a pipeline run's timeline.

    These entries are written by the SubAgentSpawner when complexity
    is high enough to trigger recursive agent spawning — the Level 5
    self-spawning layer.
    """
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")

    timeline = run.execution_timeline or []
    spawn_events = [e for e in timeline if e.get("type") in ("sub_agent_spawn", "sub_agent_result")]
    spawned_agents = [e for e in spawn_events if e.get("type") == "sub_agent_result"]

    return {
        "run_id": run_id,
        "was_triggered": any(e.get("event") == "spawn_decision" for e in spawn_events),
        "spawned_agents": spawned_agents,
        "spawn_events": spawn_events,
        "total_spawned": len(spawned_agents),
    }
