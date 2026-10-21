"""Overseer agent: decides which stages a request needs.

It returns a plan like:
    {"stages": [...], "checkpoints": ["after_planner"], "skip": [...], "reason": "..."}

`checkpoints` are the places where the run stops and waits for a human.
The plan is saved on the run (pipeline_runs.overseer_plan) and the
orchestrator follows it step by step.
"""

from __future__ import annotations

import asyncio
import json

from app.agents.llm_output import parse_json_object
from app.services.llm import build_assistant_agent
from app.utils.logging import log_structured

KNOWN_STAGES = ("planner", "designer", "developer", "critic", "tester", "self_evolve")
VALID_CHECKPOINTS = tuple(f"after_{stage}" for stage in KNOWN_STAGES if stage != "self_evolve")

OVERSEER_SYSTEM_PROMPT = """You are the Overseer of an AI software engineering pipeline.

Your job is to analyse an incoming request and produce a structured PIPELINE PLAN.

Available stages (in their default order):
  planner     - breaks the request into tasks
  designer    - creates architecture / API contracts
  developer   - writes the code
  critic      - reviews code quality and suggests improvements
  tester      - writes and runs tests
  self_evolve - stores learned patterns for future runs

Rules:
- For a FEATURE request: default order is planner, designer, developer, critic, tester, self_evolve
- For a BUG request: default order is developer, critic, tester, self_evolve (skip planner and designer)
- You may SKIP stages if they are clearly unnecessary (e.g. skip designer for a trivial one-line bug fix)
- You may ADD a CHECKPOINT after any stage where human review is valuable.
  A checkpoint pauses the pipeline and asks the human to approve or provide input before proceeding.
- Checkpoints are expensive - only add them where a human decision genuinely matters
  (e.g. after planner if the scope is large, after designer if the architecture is complex)
- For simple/trivial requests, add NO checkpoints (zero is fine)

Respond ONLY with a JSON object in this exact format (no markdown, no extra text):
{"stages":["planner","designer","developer","critic","tester","self_evolve"],"checkpoints":["after_planner"],
"skip":[],"reason":"Complex feature - architecture review recommended before coding begins."}

The "checkpoints" list contains stage names prefixed with "after_" to indicate
the pipeline should pause AFTER that stage completes and wait for human input.
Valid checkpoint values: after_planner, after_designer, after_developer, after_critic, after_tester
"""


class OverseerAgent:
    """Analyses incoming requests and produces pipeline execution plans."""

    def __init__(self) -> None:
        self._assistant = build_assistant_agent("overseer_agent", OVERSEER_SYSTEM_PROMPT)

    def _call_llm(self, description: str, request_type: str) -> str:
        user_msg = (
            f"Request type: {request_type}\n"
            f"Description: {description}\n\n"
            "Produce the pipeline plan as a single-line JSON object."
        )
        reply = self._assistant.generate_reply(
            messages=[{"role": "user", "content": user_msg}]
        )
        if isinstance(reply, dict):
            return json.dumps(reply)
        return str(reply)

    async def plan(self, description: str, request_type: str = "feature") -> dict:
        """Return a pipeline plan dict with keys: stages, checkpoints, skip, reason."""
        fallback = self._default_plan(request_type)
        try:
            raw = await asyncio.to_thread(self._call_llm, description, request_type)
            parsed = self._parse_plan(raw)
            if parsed:
                log_structured("overseer_plan_generated", stages=parsed["stages"],
                               checkpoints=parsed["checkpoints"])
                return parsed
        except Exception as exc:
            log_structured("overseer_llm_error", error=str(exc))
        return fallback

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_plan(self, raw: str) -> dict | None:
        """Read the plan from the LLM reply. Returns None if it is not usable."""
        try:
            data = parse_json_object(raw)
        except ValueError:
            return None
        if not isinstance(data.get("stages"), list):
            return None

        # Drop stage names the pipeline does not know, so a typo from the
        # LLM cannot make a stage silently do nothing.
        stages = [stage for stage in data["stages"] if stage in KNOWN_STAGES]
        if not stages:
            return None
        return {
            "stages": stages,
            "checkpoints": [c for c in data.get("checkpoints", []) if c in VALID_CHECKPOINTS],
            "skip": data.get("skip", []),
            "reason": data.get("reason", "Overseer plan generated."),
        }

    @staticmethod
    def _default_plan(request_type: str) -> dict:
        """The plan to use when the LLM is not available."""
        if request_type == "bug":
            # There is no existing code to reproduce the bug against, so the
            # developer goes first and the tester checks the fix.
            return {
                "stages": ["developer", "critic", "tester", "self_evolve"],
                "checkpoints": ["after_developer"],
                "skip": ["planner", "designer"],
                "reason": "Bug fix flow: write the fix, review it, then test it.",
            }
        return {
            "stages": ["planner", "designer", "developer", "critic", "tester", "self_evolve"],
            "checkpoints": ["after_planner"],
            "skip": [],
            "reason": "Standard feature flow with plan review checkpoint.",
        }


overseer_agent = OverseerAgent()
