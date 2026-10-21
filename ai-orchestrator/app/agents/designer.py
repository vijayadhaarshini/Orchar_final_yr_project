"""Designer agent: writes a short architecture for the planned tasks."""

from __future__ import annotations

import asyncio
import json
from textwrap import dedent

from app.agents.llm_output import parse_json_object
from app.schemas.core import DesignOutput, PlannerOutput
from app.services.llm import build_assistant_agent

SYSTEM_PROMPT = (
    "You are a senior software architect. "
    "Given a feature description and a list of planned tasks, produce a concise system design. "
    "Your ONLY output must be strict JSON with this shape:\n"
    "{\n"
    '  "architecture": "Short description of overall architecture",\n'
    '  "components": ["Component1", "Component2"],\n'
    '  "api_contracts": "Key API contracts or interfaces as plain text"\n'
    "}\n"
    "Do not include any text outside the JSON. Do not use Markdown or code fences."
)


def _as_text(value: object) -> str:
    """LLMs sometimes return a list or object where we asked for text."""
    return value if isinstance(value, str) else json.dumps(value)


class DesignerAgent:
    def __init__(self) -> None:
        self._assistant = build_assistant_agent("designer_agent", SYSTEM_PROMPT)

    def _ask_llm(self, feature_description: str, planned_tasks: PlannerOutput) -> str:
        tasks_text = "\n".join(f"- [{t.priority}] {t.description}" for t in planned_tasks.tasks)
        prompt = dedent(f"""
            Produce a system design for the following feature.

            Feature:
            {feature_description}

            Planned tasks:
            {tasks_text}

            Return ONLY valid JSON as specified.
        """).strip()
        return str(self._assistant.generate_reply(messages=[{"role": "user", "content": prompt}]))

    async def run(self, feature_description: str, planned_tasks: PlannerOutput) -> DesignOutput:
        """Ask for a design. Raises ValueError if the reply cannot be read."""
        design = parse_json_object(await asyncio.to_thread(self._ask_llm, feature_description, planned_tasks))
        components = design.get("components", [])
        return DesignOutput(
            architecture=_as_text(design.get("architecture", "")),
            components=[_as_text(c) for c in components] if isinstance(components, list) else [_as_text(components)],
            api_contracts=_as_text(design.get("api_contracts", "")),
        )


designer_agent = DesignerAgent()
