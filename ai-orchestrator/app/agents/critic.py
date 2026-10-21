"""Critic agent: scores code from 1 to 10 and suggests a better version.

It works in two steps:
  1. Ask for a score and a short critique as JSON. We do not ask for code
     inside the JSON, because code breaks JSON quoting very easily.
  2. If the score is below the threshold, ask a second assistant to
     rewrite the code, as plain code.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypedDict

from app.agents.llm_output import is_valid_python, parse_json_object, strip_code_fences
from app.config import settings
from app.services.llm import build_assistant_agent
from app.utils.logging import log_structured

if TYPE_CHECKING:
    from app.memory.agent_bus import AgentBus

REVIEW_PROMPT = (
    "You are a strict senior code reviewer. "
    "Given Python code, identify flaws, gaps, or improvements. "
    "Your ONLY output must be a JSON object with exactly these two keys:\n"
    '  "critique" – a plain-text summary of all issues found\n'
    '  "score"    – an integer from 1 to 10 rating the quality\n'
    'Example: {"critique": "Missing error handling and type hints", "score": 6}\n'
    "Output ONLY the JSON — no markdown, no code fences, no extra text."
)

IMPROVE_PROMPT = (
    "You are a senior Python developer. "
    "You receive Python code and a critique. "
    "Rewrite the code to address ALL critique points. "
    "Return ONLY valid Python code — no markdown fences, no explanation."
)


class Critique(TypedDict):
    critique: str
    score: int
    improved: str  # better code, or the original code if no valid rewrite was made


class CriticAgent:
    def __init__(self) -> None:
        self._reviewer = build_assistant_agent("critic_agent", REVIEW_PROMPT)
        self._improver = build_assistant_agent("critic_improver", IMPROVE_PROMPT)

    def _ask_for_review(self, code: str) -> str:
        prompt = f"Review the following Python code. Return ONLY the JSON.\n\nPYTHON CODE:\n{code}"
        return str(self._reviewer.generate_reply(messages=[{"role": "user", "content": prompt}]))

    def _ask_for_rewrite(self, code: str, critique: str) -> str:
        prompt = (
            f"Critique of the code:\n{critique}\n\n"
            f"Original code:\n{code}\n\n"
            "Rewrite the code to fully address the critique. Return ONLY Python code."
        )
        reply = self._improver.generate_reply(messages=[{"role": "user", "content": prompt}])
        return strip_code_fences(str(reply))

    async def critique_code(self, code: str, bus: AgentBus | None = None) -> Critique:
        """Score the code and, if the score is low, suggest a rewrite.

        Raises ValueError if the review reply cannot be read. We raise instead
        of returning a made-up score, so callers never mistake an error
        message for real feedback.
        """
        review = parse_json_object(await asyncio.to_thread(self._ask_for_review, code))
        critique = str(review.get("critique", ""))
        try:
            score = max(1, min(10, int(review["score"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Critic reply has no usable score: {review!r}") from exc

        threshold = settings.DEBATE_SCORE_THRESHOLD
        improved = code
        if score < threshold:
            try:
                rewrite = await asyncio.to_thread(self._ask_for_rewrite, code, critique)
            except Exception as exc:
                log_structured("critic_rewrite_error", error=str(exc))
            else:
                # Only use the rewrite if it is real Python. Otherwise keep the original.
                if is_valid_python(rewrite):
                    improved = rewrite
                else:
                    log_structured("critic_rewrite_invalid_python")

        log_structured("critic_scored", score=score, critique_length=len(critique))

        if bus is not None:
            # Also send the critique straight to the developer's inbox.
            await bus.send(
                from_agent="critic",
                to_agent="developer",
                message_type="detailed_critique",
                content={"score": score, "critique": critique, "threshold": threshold,
                         "needs_revision": score < threshold},
            )

        return Critique(critique=critique, score=score, improved=improved)


critic_agent = CriticAgent()
