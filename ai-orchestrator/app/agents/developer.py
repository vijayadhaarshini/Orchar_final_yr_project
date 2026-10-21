"""Developer agent: writes Python code for the planned tasks, and revises it.

`revise` is used twice in the pipeline:
  - in the debate loop, with the critic's feedback
  - in the recovery loop, with the failing test output
"""

from __future__ import annotations

import asyncio
from textwrap import dedent
from typing import TYPE_CHECKING

from app.agents.llm_output import is_valid_python, strip_code_fences
from app.schemas.core import PlannerOutput
from app.services.llm import build_assistant_agent
from app.utils.logging import log_structured

if TYPE_CHECKING:
    from app.memory.agent_bus import AgentBus

SYSTEM_PROMPT = (
    "You are a senior Python developer. "
    "Generate production-ready, PEP8-compliant Python 3.11 code that fulfills the requested tasks. "
    "Return ONLY pure Python code, no explanations, no comments about usage, and no Markdown fences. "
    "Include docstrings for all public functions and classes."
)


class DeveloperAgent:
    def __init__(self) -> None:
        self._assistant = build_assistant_agent("developer_agent", SYSTEM_PROMPT)

    def _ask_llm(self, prompt: str) -> str:
        reply = self._assistant.generate_reply(messages=[{"role": "user", "content": prompt}])
        return strip_code_fences(str(reply))

    async def _ask_for_valid_code(self, prompt: str) -> str:
        """Ask the LLM for code. Raises ValueError if the reply is not valid Python."""
        code = await asyncio.to_thread(self._ask_llm, prompt)
        if not is_valid_python(code):
            log_structured("developer_syntax_error", code_preview=code[:200])
            raise ValueError("Developer returned code that is not valid Python.")
        return code

    async def run(self, feature_description: str, planner_output: PlannerOutput) -> str:
        """Write code for the feature. The orchestrator retries this if it raises."""
        tasks_text = "\n".join(f"- [{t.priority}] {t.id}: {t.description}" for t in planner_output.tasks)
        prompt = dedent(f"""
            Implement the feature described below. Focus on clarity and testability.

            Feature:
            {feature_description}

            Planned tasks:
            {tasks_text}

            Return ONLY valid Python code that can be parsed by ast.parse.
        """).strip()
        return await self._ask_for_valid_code(prompt)

    async def revise(
        self,
        current_code: str,
        feedback: str,
        feature_description: str,
        evolved_instructions: list[str] | None = None,
        bus: AgentBus | None = None,
    ) -> str:
        """Rewrite `current_code` so it addresses `feedback`.

        Raises ValueError if the new code is not valid Python. Callers then
        keep `current_code`, so a bad revision never replaces working code.

        If a message bus is given, the critic's messages sent straight to the
        developer are added to the feedback.
        """
        if bus is not None:
            feedback += _critic_messages_from_bus(bus)

        learned = ""
        if evolved_instructions:
            learned = (
                f"Previously learned instructions for this type of task (from {len(evolved_instructions)} "
                "past run(s)):\n" + "\n".join(f"  • {item}" for item in evolved_instructions[-5:]) + "\n\n"
            )

        prompt = dedent(f"""
            {learned}You previously wrote code for the following task:
            {feature_description[:300]}

            CURRENT CODE:
            {current_code}

            FEEDBACK TO ADDRESS:
            {feedback}

            Revise the code to fully address every point in the feedback above.
            Return ONLY valid Python code. No explanations. No Markdown fences.
        """).strip()

        log_structured("developer_revise_start", code_lines=len(current_code.splitlines()))
        return await self._ask_for_valid_code(prompt)


def _critic_messages_from_bus(bus: AgentBus) -> str:
    """Read unread critic messages from the developer's inbox, as extra feedback text."""
    points = [
        f"[Direct critic message — score {msg.content.get('score', '?')}/10]: {msg.content.get('critique', '')}"
        for msg in bus.receive("developer")
        if msg.message_type == "detailed_critique" and isinstance(msg.content, dict)
    ]
    if not points:
        return ""
    log_structured("developer_bus_messages_received", count=len(points))
    return "\n\nAdditional structured feedback from Critic (via P2P bus):\n" + "\n".join(points)


developer_agent = DeveloperAgent()
