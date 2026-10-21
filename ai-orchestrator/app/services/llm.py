"""Creates the AutoGen assistants that every agent uses to talk to the LLM.

Groq's API is OpenAI-compatible, so AutoGen's normal OpenAI client is
pointed at Groq through `base_url`.
"""

from __future__ import annotations

import autogen

from app.config import settings


def build_assistant_agent(name: str, system_message: str) -> autogen.AssistantAgent:
    """An assistant with the given system prompt, set up for Groq."""
    llm_config = {
        "config_list": [
            {"model": settings.GROQ_MODEL, "api_key": settings.GROQ_API_KEY, "base_url": settings.GROQ_BASE_URL}
        ],
        "temperature": 0.1,
        # Network timeout for each LLM call. This is the only timeout on agent
        # calls (see _run_with_retries in orchestrator/service.py).
        "timeout": settings.AGENT_TIMEOUT_SECONDS,
    }
    return autogen.AssistantAgent(name=name, system_message=system_message, llm_config=llm_config)
