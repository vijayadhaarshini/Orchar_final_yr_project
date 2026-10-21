"""Sub-Agent Spawner — Level 5 Recursive Sub-Agent Spawning.

When the Planner detects a complex feature, it signals that specialist
sub-agents should be spawned dynamically. The spawner:

  1. Analyses each planned task to determine if it needs a specialist
  2. Spawns ephemeral, task-scoped agents on-the-fly (database agent,
     auth agent, cache agent, etc.) with role-specific system prompts
  3. Each sub-agent independently drafts code for its sub-task
  4. Sub-agent outputs are merged by a Composer into a single module

Static sub-agent types triggered by keywords in task descriptions:
  - "database" / "model" / "orm"       → DatabaseAgent
  - "auth" / "login" / "jwt" / "token" → AuthAgent
  - "cache" / "redis" / "lru"          → CacheAgent
  - "api" / "endpoint" / "route"       → APIAgent
  - "email" / "smtp" / "notification"  → NotificationAgent
  - "file" / "upload" / "storage"      → StorageAgent
  - (default)                          → GeneralAgent (standard developer)

Dynamic roles: at spawn time, SPECIALIST_ROLES is merged with any roles
persisted in dynamic_roles.json (written by role_discovery.py / self_evolve.py).
Unmatched "general" tasks are forwarded to RoleDiscoveryAgent so new
specialist types can be invented on-the-fly.

P2P bus: each spawned sub-agent posts its result to the AgentBus (if provided),
allowing the Composer and other agents to read them directly.

Timeline entries use type="sub_agent_spawn" and type="sub_agent_result".
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from textwrap import dedent
from typing import TYPE_CHECKING, Optional

from app.agents.llm_output import is_valid_python, strip_code_fences
from app.memory.dynamic_roles import load_dynamic_roles
from app.services.llm import build_assistant_agent
from app.utils.logging import log_structured

if TYPE_CHECKING:
    from app.memory.agent_bus import AgentBus


# ---------------------------------------------------------------------------
# Sub-agent role definitions
# ---------------------------------------------------------------------------

SPECIALIST_ROLES: dict[str, dict] = {
    "database": {
        "keywords": ["database", "db", "model", "orm", "sqlalchemy", "table", "schema", "migration", "query"],
        "system_prompt": (
            "You are a specialist Database Engineer. "
            "Your ONLY job is to write Python code for database models, queries, and ORM definitions. "
            "Use SQLAlchemy async patterns. "
            "Return ONLY valid Python code, no markdown, no explanations."
        ),
        "label": "Database Agent",
    },
    "auth": {
        "keywords": ["auth", "authentication", "login", "jwt", "token", "password", "session", "oauth", "permission"],
        "system_prompt": (
            "You are a specialist Security/Auth Engineer. "
            "Your ONLY job is to write Python code for authentication, authorization, JWT tokens, "
            "password hashing, and session management. "
            "Use industry best practices (bcrypt, HS256, expiry). "
            "Return ONLY valid Python code, no markdown, no explanations."
        ),
        "label": "Auth Agent",
    },
    "cache": {
        "keywords": ["cache", "redis", "lru", "ttl", "memoize", "invalidate", "evict"],
        "system_prompt": (
            "You are a specialist Caching Engineer. "
            "Your ONLY job is to write Python code for caching layers — Redis, in-memory LRU, TTL expiry, "
            "cache invalidation strategies. "
            "Return ONLY valid Python code, no markdown, no explanations."
        ),
        "label": "Cache Agent",
    },
    "api": {
        "keywords": ["api", "endpoint", "route", "rest", "fastapi", "http", "request", "response", "middleware"],
        "system_prompt": (
            "You are a specialist API Engineer. "
            "Your ONLY job is to write Python code for FastAPI routes, request/response schemas, "
            "middleware, and dependency injection. "
            "Follow RESTful conventions strictly. "
            "Return ONLY valid Python code, no markdown, no explanations."
        ),
        "label": "API Agent",
    },
    "notification": {
        "keywords": ["email", "smtp", "notification", "alert", "webhook", "send", "message", "push"],
        "system_prompt": (
            "You are a specialist Notification Engineer. "
            "Your ONLY job is to write Python code for email sending, webhooks, push notifications, "
            "and async messaging systems. "
            "Return ONLY valid Python code, no markdown, no explanations."
        ),
        "label": "Notification Agent",
    },
    "storage": {
        "keywords": ["file", "upload", "download", "storage", "s3", "bucket", "blob", "disk", "image"],
        "system_prompt": (
            "You are a specialist Storage Engineer. "
            "Your ONLY job is to write Python code for file I/O, cloud storage (S3/GCS), "
            "file validation, and streaming uploads. "
            "Return ONLY valid Python code, no markdown, no explanations."
        ),
        "label": "Storage Agent",
    },
}

COMPOSER_SYSTEM_PROMPT = (
    "You are a Code Composer. You receive several Python code fragments written by specialist agents. "
    "Your job is to merge them into ONE coherent, standalone, importable Python module. "
    "Rules: "
    "(1) Consolidate all imports at the top of the file — no duplicate imports. "
    "(2) Remove duplicate class/function definitions — keep the most complete version. "
    "(3) Ensure every name that is referenced is defined somewhere in the module. "
    "(4) The module must be importable standalone with no NameError or ImportError. "
    "(5) Do NOT leave placeholder strings like 'IMPROVED_SEPARATELY' or TODO comments. "
    "Return ONLY valid Python code — no markdown fences, no explanations, no comments about merging."
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SpawnedSubAgent:
    role: str
    label: str
    task_description: str
    code_output: str = ""
    error: Optional[str] = None


@dataclass
class SpawnerResult:
    spawned_agents: list[SpawnedSubAgent] = field(default_factory=list)
    composed_code: str = ""
    was_triggered: bool = False
    complexity_score: int = 0


# ---------------------------------------------------------------------------
# Core spawner
# ---------------------------------------------------------------------------

class SubAgentSpawner:
    """Dynamically spawns specialist sub-agents for complex tasks.

    Call analyse_and_spawn() after the planner stage.
    It returns a SpawnerResult; if was_triggered=True, use composed_code
    as the generated_code instead of running the standard developer agent.

    Dynamic roles: merges SPECIALIST_ROLES with any roles in dynamic_roles.json
    so newly discovered specialist types are available without code changes.

    P2P bus: if a bus is passed to analyse_and_spawn(), each spawned sub-agent
    posts its result to the bus for direct consumption by downstream agents.
    """

    # Minimum number of tasks in a plan before spawning is considered
    SPAWN_TASK_THRESHOLD = 2
    # Minimum distinct specialist roles detected before spawning fires
    SPAWN_ROLE_THRESHOLD = 2

    def __init__(self) -> None:
        self._composer = build_assistant_agent("composer_agent", COMPOSER_SYSTEM_PROMPT)

    def _get_all_roles(self) -> dict[str, dict]:
        """Return SPECIALIST_ROLES merged with persisted dynamic roles."""
        merged = dict(SPECIALIST_ROLES)
        try:
            dynamic = load_dynamic_roles()
            for role_name, role_def in dynamic.items():
                if role_name not in merged:
                    merged[role_name] = role_def
                    log_structured("dynamic_role_loaded", role=role_name)
        except Exception as exc:
            log_structured("dynamic_roles_merge_error", error=str(exc))
        return merged

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyse_and_spawn(
        self,
        project_id: int,
        feature_description: str,
        planned_tasks: list[dict],
        timeline: list[dict],
        evolved_instructions: str = "",
        bus: "AgentBus | None" = None,
    ) -> SpawnerResult:
        """Analyse planned tasks, spawn specialist agents if needed.

        Args:
            project_id: Used for logging.
            feature_description: Overall feature goal.
            planned_tasks: List of task dicts with 'description' keys.
            timeline: Mutable list to append spawn events to.
            evolved_instructions: Prefix from evolved_prompts for each sub-agent.

        Returns:
            SpawnerResult with spawned_agents and composed_code.
        """
        result = SpawnerResult()

        # 1. Merge static + dynamic roles, then analyse tasks
        all_roles = self._get_all_roles()
        role_map = self._analyse_tasks(planned_tasks, all_roles)
        distinct_roles = list(role_map.keys())
        result.complexity_score = len(distinct_roles)

        log_structured(
            "sub_agent_analysis",
            project_id=project_id,
            distinct_roles=distinct_roles,
            task_count=len(planned_tasks),
        )

        # 2. Decide whether to spawn
        enough_tasks = len(planned_tasks) >= self.SPAWN_TASK_THRESHOLD
        enough_roles = len(distinct_roles) >= self.SPAWN_ROLE_THRESHOLD

        if not (enough_tasks and enough_roles):
            log_structured("sub_agent_spawn_skipped", project_id=project_id,
                           reason="below threshold")
            return result

        result.was_triggered = True

        # 3. Emit spawn decision to timeline
        timeline.append({
            "type": "sub_agent_spawn",
            "event": "spawn_decision",
            "roles": distinct_roles,
            "task_count": len(planned_tasks),
            "reason": (
                f"Complexity score {len(distinct_roles)} — detected specialist roles: "
                + ", ".join(distinct_roles)
            ),
        })

        # 3b. Attempt role discovery for any unmatched "general" tasks
        general_tasks = role_map.get("general", [])
        if general_tasks:
            try:
                from app.agents.role_discovery import role_discovery_agent  # lazy
                new_role = await role_discovery_agent.discover(
                    unmatched_tasks=general_tasks,
                    extra_known_roles=list(all_roles.keys()),
                )
                if new_role:
                    # Re-run task analysis with the newly discovered role included
                    all_roles = self._get_all_roles()
                    role_map = self._analyse_tasks(planned_tasks, all_roles)
                    distinct_roles = list(role_map.keys())
                    timeline.append({
                        "type": "sub_agent_spawn",
                        "event": "new_role_discovered",
                        "role": new_role.get("role_name"),
                        "label": new_role.get("label"),
                    })
            except Exception as exc:
                log_structured("spawner_role_discovery_error",
                               project_id=project_id, error=str(exc))

        # 4. Spawn each specialist agent concurrently
        spawn_coroutines = [
            self._run_specialist(
                role=role,
                tasks=tasks,
                feature_description=feature_description,
                evolved_instructions=evolved_instructions,
                all_roles=all_roles,
            )
            for role, tasks in role_map.items()
        ]
        spawned: list[SpawnedSubAgent] = await asyncio.gather(*spawn_coroutines)
        result.spawned_agents = list(spawned)

        # 5. Emit per-agent results to timeline and bus
        for agent in spawned:
            timeline.append({
                "type": "sub_agent_result",
                "role": agent.role,
                "label": agent.label,
                "task": agent.task_description,
                "success": agent.error is None,
                "code_length": len(agent.code_output),
                "error": agent.error,
            })
            # P2P bus: post each sub-agent's code output for direct consumption
            if bus is not None and agent.error is None and agent.code_output.strip():
                try:
                    await bus.send(
                        from_agent=f"sub_agent_{agent.role}",
                        to_agent="composer",
                        message_type="sub_agent_code",
                        content={
                            "role": agent.role,
                            "label": agent.label,
                            "code_length": len(agent.code_output),
                        },
                    )
                except Exception as bus_exc:
                    log_structured("spawner_bus_send_error",
                                   role=agent.role, error=str(bus_exc))

        # 6. Compose all fragments into a single module
        successful = [a for a in spawned if a.error is None and a.code_output.strip()]
        if successful:
            result.composed_code = await self._compose(successful, feature_description)
        if not result.composed_code:
            # Nothing usable came out, so the normal developer stage writes the code instead.
            result.was_triggered = False
            timeline.append({
                "type": "sub_agent_spawn",
                "event": "spawn_fallback",
                "reason": "Sub-agents did not produce valid code — falling back to standard developer",
            })

        log_structured(
            "sub_agent_spawn_complete",
            project_id=project_id,
            spawned=len(spawned),
            composed_length=len(result.composed_code),
        )
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _analyse_tasks(
        self,
        planned_tasks: list[dict],
        all_roles: dict[str, dict] | None = None,
    ) -> dict[str, list[str]]:
        """Map each task to a specialist role. Returns {role: [task_desc, ...]}.

        Uses the merged static + dynamic roles dict if provided, otherwise
        falls back to the static SPECIALIST_ROLES.
        """
        roles = all_roles if all_roles is not None else SPECIALIST_ROLES
        role_map: dict[str, list[str]] = {}

        for task in planned_tasks:
            desc = task.get("description", "").lower()
            matched = False
            for role, cfg in roles.items():
                if role == "general":
                    continue  # Never eagerly assign to "general"
                if any(kw in desc for kw in cfg.get("keywords", [])):
                    role_map.setdefault(role, []).append(task.get("description", ""))
                    matched = True
                    break
            if not matched:
                role_map.setdefault("general", []).append(task.get("description", ""))

        return role_map

    async def _run_specialist(
        self,
        role: str,
        tasks: list[str],
        feature_description: str,
        evolved_instructions: str,
        all_roles: dict[str, dict] | None = None,
    ) -> SpawnedSubAgent:
        """Spawn a single specialist agent and get its code output."""
        roles = all_roles if all_roles is not None else SPECIALIST_ROLES
        cfg = roles.get(role, {
            "system_prompt": (
                "You are a senior Python developer. "
                "Return ONLY valid Python code, no markdown, no explanations."
            ),
            "label": f"{role.capitalize()} Agent",
        })

        agent = build_assistant_agent(f"sub_{role}_agent", cfg["system_prompt"])
        tasks_text = "\n".join(f"- {t}" for t in tasks)

        prefix = f"[Evolved instructions]\n{evolved_instructions}\n\n" if evolved_instructions else ""
        prompt = dedent(f"""
            {prefix}Overall feature goal:
            {feature_description}

            Your specific tasks (implement ALL of them):
            {tasks_text}

            Return ONLY valid Python code for these tasks.
        """).strip()

        spawned = SpawnedSubAgent(
            role=role,
            label=cfg["label"],
            task_description="; ".join(tasks),
        )

        try:
            reply = await asyncio.to_thread(
                lambda: agent.generate_reply(messages=[{"role": "user", "content": prompt}])
            )
            code = strip_code_fences(str(reply))
            spawned.code_output = code
            log_structured("sub_agent_done", role=role, code_length=len(code))
        except Exception as exc:
            spawned.error = str(exc)
            log_structured("sub_agent_error", role=role, error=str(exc))

        return spawned

    async def _compose(self, agents: list[SpawnedSubAgent], feature_description: str) -> str:
        """Merge the sub-agents' code into one module.

        Returns "" if neither the Composer's merge nor a plain join of the
        fragments is valid Python. The caller then lets the developer
        write the code, so broken code never skips the developer stage.
        """
        fragments = "\n\n".join(f"# === {a.label} ({a.role}) ===\n{a.code_output}" for a in agents)
        prompt = dedent(f"""
            Merge the following code fragments into a single coherent Python module.
            The overall feature is: {feature_description}

            Fragments:
            {fragments}

            Return ONLY the merged Python code.
        """).strip()

        try:
            reply = await asyncio.to_thread(
                self._composer.generate_reply, messages=[{"role": "user", "content": prompt}]
            )
            merged = strip_code_fences(str(reply))
            if is_valid_python(merged):
                return merged
            log_structured("sub_agent_compose_invalid_python")
        except Exception as exc:
            log_structured("sub_agent_compose_error", error=str(exc))

        joined = "\n\n".join(a.code_output for a in agents)
        return joined if is_valid_python(joined) else ""


# Module-level singleton
sub_agent_spawner = SubAgentSpawner()
