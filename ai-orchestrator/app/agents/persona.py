"""Output style for each persona (the "Output Mode" the user picks in the sidebar).

The chosen text is added to the start of every agent's prompt, so the same
request gets simpler or more detailed answers depending on who is asking.
"""

from __future__ import annotations

PERSONA_PROMPTS = {
    "simple": (
        "You are explaining to a non-technical manager. "
        "Use plain English, avoid jargon, focus on business impact and high-level steps only."
    ),
    "intermediate": (
        "You are explaining to a developer with general programming experience. "
        "Use clear technical language. Include implementation details but avoid deep internals."
    ),
    "expert": (
        "You are explaining to a senior engineer. Use precise technical terminology. "
        "Include architecture decisions, trade-offs, and deep implementation details."
    ),
}


def persona_context(persona: str) -> str:
    """The style text for `persona`. Unknown values fall back to "intermediate"."""
    return PERSONA_PROMPTS.get(persona, PERSONA_PROMPTS["intermediate"])
