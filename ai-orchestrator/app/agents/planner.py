"""Planner agent: turns a feature request into a short list of tasks."""

from __future__ import annotations

import asyncio

from pydantic import ValidationError
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm_output import parse_json_object
from app.models.core import Task
from app.schemas.core import PlannerOutput
from app.services.llm import build_assistant_agent
from app.utils.logging import log_structured

SYSTEM_PROMPT = (
    "You are a senior software planner. "
    "Your ONLY output must be strict JSON with the following shape:\n"
    '{\n  "tasks": [\n    {"id": "string", "description": "string", "priority": "low|medium|high"}\n  ]\n}\n'
    "Do not include any natural language outside the JSON. Do not use Markdown or code fences."
)


class PlannerAgent:
    def __init__(self) -> None:
        self._assistant = build_assistant_agent("planner_agent", SYSTEM_PROMPT)

    def _ask_llm(self, feature_description: str) -> str:
        prompt = (
            "Create a minimal, well-structured implementation plan for the following feature. "
            "Return ONLY valid JSON as specified.\n\n"
            f"Feature:\n{feature_description}"
        )
        reply = self._assistant.generate_reply(messages=[{"role": "user", "content": prompt}])
        return str(reply)

    async def run(self, db: AsyncSession, project_id: int, feature_description: str) -> PlannerOutput:
        """Ask the LLM for a plan, check it, and save the tasks.

        Raises ValueError if the reply is not a valid plan. The orchestrator
        retries the whole call, so a bad reply leads to a new LLM call.
        """
        raw = await asyncio.to_thread(self._ask_llm, feature_description)
        try:
            plan = PlannerOutput(**parse_json_object(raw))
        except (ValueError, ValidationError) as exc:
            log_structured("planner_parse_error", error=str(exc), raw_output=raw[:500])
            raise ValueError(f"Planner reply was not a valid plan: {exc}") from exc

        if plan.tasks:
            await db.execute(
                insert(Task).values([
                    {"project_id": project_id, "description": t.description, "priority": t.priority,
                     "status": "planned"}
                    for t in plan.tasks
                ])
            )
            await db.commit()
        return plan


planner_agent = PlannerAgent()
