"""Role discovery agent: invents new specialist roles at runtime.

SubAgentSpawner has a fixed set of specialists (database, auth, cache, ...).
When a task fits none of them, this agent may define a new one (name,
keywords, system prompt). New roles are saved to dynamic_roles.json and are
available to every later run.

Called by self_evolve.py after a run, and by sub_agent_spawner.py when
tasks do not match any role.
"""

from __future__ import annotations

import asyncio
from textwrap import dedent

from app.agents.llm_output import parse_json_object
from app.agents.sub_agent_spawner import SPECIALIST_ROLES
from app.memory.dynamic_roles import load_dynamic_roles, save_dynamic_role
from app.services.llm import build_assistant_agent
from app.utils.logging import log_structured

ROLE_DISCOVERY_SYSTEM_PROMPT = (
    "You are an AI agent architect. "
    "You analyse software task descriptions and decide whether a new specialist "
    "Python agent role should be created to handle that type of task more effectively. "
    "\n\n"
    "When a new role IS warranted, output ONLY a JSON object with this exact shape:\n"
    "{\n"
    '  "role_name": "short_snake_case_name",\n'
    '  "label": "Human Readable Agent Name",\n'
    '  "keywords": ["keyword1", "keyword2", "keyword3"],\n'
    '  "system_prompt": "You are a specialist <Role> Engineer. Your ONLY job is to write Python code for '
    '<domain>. Return ONLY valid Python code, no markdown, no explanations."\n'
    "}\n\n"
    "When no new role is needed (tasks fit existing roles adequately), output ONLY the word: null\n"
    "Do not output anything other than the JSON object or the word null."
)

# Roles built into SubAgentSpawner, plus the "general" fallback.
# The LLM must not create a role with one of these names.
STATIC_ROLE_NAMES: frozenset[str] = frozenset(SPECIALIST_ROLES) | {"general"}


class RoleDiscoveryAgent:
    """Analyses unmatched tasks and generates new specialist role definitions.

    The generated roles are immediately persisted and will be picked up by
    SubAgentSpawner on the next (or current) pipeline run.
    """

    def __init__(self) -> None:
        self._assistant = build_assistant_agent(
            "role_discovery_agent", ROLE_DISCOVERY_SYSTEM_PROMPT
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call_llm(self, task_descriptions: list[str], existing_role_names: list[str]) -> str:
        tasks_text = "\n".join(f"  - {t}" for t in task_descriptions)
        prompt = dedent(f"""
            Existing specialist roles already available: {", ".join(existing_role_names)}

            Tasks that did NOT match any existing specialist role:
            {tasks_text}

            Should a new specialist agent role be created for these tasks?
            If yes, generate a role definition JSON as specified.
            If no (the tasks are adequately covered by existing roles or are too generic),
            output only: null
        """).strip()
        reply = self._assistant.generate_reply(
            messages=[{"role": "user", "content": prompt}]
        )
        return str(reply).strip()

    @staticmethod
    def _parse_role(raw: str) -> dict | None:
        """The new role from the reply, or None if the LLM said no new role is needed."""
        if raw.strip().lower() in ("null", "none", ""):
            return None
        try:
            role = parse_json_object(raw)
        except ValueError:
            return None
        if not all(key in role for key in ("role_name", "label", "keywords", "system_prompt")):
            return None
        if not isinstance(role["keywords"], list) or not role["keywords"]:
            return None
        return role

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def discover(
        self,
        unmatched_tasks: list[str],
        extra_known_roles: list[str] | None = None,
    ) -> dict | None:
        """Attempt to generate and persist a new specialist role.

        Args:
            unmatched_tasks:   Task descriptions that didn't match any existing role.
            extra_known_roles: Additional role names to treat as already known
                               (prevents duplicating roles the caller already has).

        Returns:
            The new role definition dict if one was generated and saved, else None.
        """
        if not unmatched_tasks:
            return None

        # Build the full list of known role names to avoid duplicates
        all_known: list[str] = list(STATIC_ROLE_NAMES) + list(load_dynamic_roles().keys())
        if extra_known_roles:
            all_known = list(set(all_known + extra_known_roles))

        try:
            raw = await asyncio.to_thread(self._call_llm, unmatched_tasks, all_known)
            role_def = self._parse_role(raw)
        except Exception as exc:
            log_structured("role_discovery_llm_error", error=str(exc))
            return None

        if role_def is None:
            log_structured(
                "role_discovery_no_new_role",
                task_count=len(unmatched_tasks),
            )
            return None

        role_name = role_def["role_name"].lower().replace(" ", "_").replace("-", "_")

        if role_name in all_known:
            log_structured("role_discovery_duplicate_skipped", role=role_name)
            return None

        # Persist the new role
        role_def["role_name"] = role_name
        save_dynamic_role(role_name, {
            "keywords": role_def["keywords"],
            "system_prompt": role_def["system_prompt"],
            "label": role_def["label"],
        })
        log_structured(
            "role_discovery_new_role_created",
            role=role_name,
            label=role_def["label"],
            keywords=role_def["keywords"],
        )
        return role_def


# Module-level singleton
role_discovery_agent = RoleDiscoveryAgent()
