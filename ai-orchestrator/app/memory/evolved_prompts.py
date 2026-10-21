"""Structural Prompt Evolution Store.

Per-project, per-agent learned instructions persisted as JSON files in the
ChromaDB data directory.  Unlike the ChromaDB vector store (which stores
*context* for retrieval), this module stores *structural instructions* that are
prepended directly to an agent's working prompt on every run — changing how the
agent thinks, not just what it knows.

Self-Evolve writes here after each run.
service.py reads here before calling each agent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from app.config import settings
from app.utils.logging import log_structured

# ---------------------------------------------------------------------------
# Keyword → agent routing table
# When a new instruction is learned, these keywords decide which agents receive
# it as a structural prompt update.
# ---------------------------------------------------------------------------

TASK_TYPE_AGENT_MAP: dict[str, list[str]] = {
    "api":          ["developer", "tester"],
    "rest":         ["developer", "tester"],
    "endpoint":     ["developer", "tester"],
    "route":        ["developer", "tester"],
    "fastapi":      ["developer", "tester"],
    "flask":        ["developer", "tester"],
    "validation":   ["developer"],
    "pydantic":     ["developer"],
    "database":     ["developer"],
    "sql":          ["developer"],
    "test":         ["tester"],
    "testing":      ["tester"],
    "coverage":     ["tester"],
    "quality":      ["critic", "developer"],
    "review":       ["critic"],
    "refactor":     ["developer", "critic"],
    "design":       ["designer"],
    "architecture": ["designer", "planner"],
    "plan":         ["planner"],
    "bug":          ["developer", "tester"],
    "fix":          ["developer", "tester"],
    "error":        ["developer", "tester"],
    "auth":         ["developer"],
    "security":     ["developer", "critic"],
    "async":        ["developer", "tester"],
    "performance":  ["developer", "critic"],
    "class":        ["developer"],
    "function":     ["developer"],
    "general":      ["developer"],
}

MAX_INSTRUCTIONS_PER_AGENT = 10  # Cap to avoid prompt bloat


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _prompts_path(project_id: int) -> Path:
    chroma_dir = Path(settings.CHROMA_DIR)
    chroma_dir.mkdir(parents=True, exist_ok=True)
    return chroma_dir / f"evolved_prompts_{project_id}.json"


def load_evolved_prompts(project_id: int) -> Dict[str, List[str]]:
    """Load all evolved instructions for a project, keyed by agent name."""
    path = _prompts_path(project_id)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:
        log_structured("evolved_prompts_load_error", project_id=project_id, error=str(exc))
        return {}


def save_evolved_prompts(project_id: int, prompts: Dict[str, List[str]]) -> None:
    """Persist the full evolved prompts dict for a project."""
    path = _prompts_path(project_id)
    try:
        with open(path, "w") as f:
            json.dump(prompts, f, indent=2)
    except Exception as exc:
        log_structured("evolved_prompts_save_error", project_id=project_id, error=str(exc))


def add_agent_instruction(
    project_id: int,
    agent_name: str,
    instruction: str,
) -> None:
    """Add an evolved instruction for a specific agent, capped at MAX_INSTRUCTIONS_PER_AGENT."""
    prompts = load_evolved_prompts(project_id)
    bucket = prompts.setdefault(agent_name, [])
    # Avoid exact duplicates
    if instruction not in bucket:
        bucket.append(instruction)
    # Keep only the most recent N
    prompts[agent_name] = bucket[-MAX_INSTRUCTIONS_PER_AGENT:]
    save_evolved_prompts(project_id, prompts)
    log_structured(
        "evolved_prompt_added",
        project_id=project_id,
        agent=agent_name,
        total=len(prompts[agent_name]),
    )


def route_instruction_to_agents(
    project_id: int,
    task_type: str,
    instruction: str,
) -> list[str]:
    """Route a learned instruction to the relevant agents based on task_type keywords.

    Returns the list of agent names that received the instruction.
    """
    task_lower = task_type.lower()
    target_agents: set[str] = set()

    for keyword, agents in TASK_TYPE_AGENT_MAP.items():
        if keyword in task_lower:
            target_agents.update(agents)

    if not target_agents:
        target_agents.add("developer")  # safe default

    for agent_name in target_agents:
        add_agent_instruction(project_id, agent_name, instruction)

    log_structured(
        "evolved_instruction_routed",
        project_id=project_id,
        task_type=task_type,
        agents=list(target_agents),
    )
    return list(target_agents)
