"""Dynamic Specialist Role Store.

Persists LLM-generated specialist role definitions so that the sub-agent
spawner can use new roles discovered at runtime — not just the 6 hardcoded
ones in SPECIALIST_ROLES.

Written by: app/agents/role_discovery.py  (called from self_evolve.py)
Read by:    app/agents/sub_agent_spawner.py (merged at spawn time)

Each dynamic role has the same shape as a SPECIALIST_ROLES entry:
    {
        "keywords":      ["kw1", "kw2", ...],
        "system_prompt": "You are a specialist ...",
        "label":         "Human Readable Agent Name",
    }
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.utils.logging import log_structured


def _roles_path() -> Path:
    p = Path(settings.CHROMA_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p / "dynamic_roles.json"


def load_dynamic_roles() -> dict[str, dict]:
    """Load all persisted dynamic roles.

    Returns a dict keyed by role_name, matching the SPECIALIST_ROLES shape.
    Returns an empty dict if the file does not exist or cannot be parsed.
    """
    path = _roles_path()
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception as exc:
        log_structured("dynamic_roles_load_error", error=str(exc))
        return {}


def save_dynamic_role(role_name: str, role_def: dict) -> None:
    """Persist a new or updated dynamic role definition.

    Args:
        role_name: snake_case identifier for the role.
        role_def:  Dict with keys: keywords (list[str]), system_prompt (str), label (str).
    """
    roles = load_dynamic_roles()
    roles[role_name] = role_def
    path = _roles_path()
    try:
        with open(path, "w") as f:
            json.dump(roles, f, indent=2)
        log_structured(
            "dynamic_role_saved",
            role=role_name,
            keywords=role_def.get("keywords", []),
            label=role_def.get("label", ""),
        )
    except Exception as exc:
        log_structured("dynamic_roles_save_error", role=role_name, error=str(exc))


def list_dynamic_role_names() -> list[str]:
    """Return the names of all persisted dynamic roles."""
    return list(load_dynamic_roles().keys())
