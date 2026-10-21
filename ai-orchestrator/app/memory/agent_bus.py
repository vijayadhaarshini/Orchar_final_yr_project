"""Peer-to-Peer Agent Message Bus.

Enables direct, asynchronous communication between agents without routing
everything through the orchestrator hub.  Each pipeline run gets its own
AgentBus instance which is passed to agents that support it.

Messages are stored in-memory for the run duration and also written to a
JSON log file for observability / debugging.

Usage (inside an agent):
    # Critic sends a structured critique directly to the developer
    await bus.send(
        from_agent="critic",
        to_agent="developer",
        message_type="detailed_critique",
        content={"score": 4, "points": ["missing type hints", "no error handling"]},
    )

    # Developer checks its own inbox before revising
    messages = bus.receive("developer")
    for msg in messages:
        # incorporate msg.content into revision prompt …

Timeline entries use type="p2p_message" and are appended to the pipeline
execution_timeline at run completion.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logging import log_structured


def _log_file(log_dir: Path, run_id: int) -> Path:
    return log_dir / f"bus_run_{run_id}.json"


def load_bus_messages(log_dir: str, run_id: int) -> list[dict]:
    """Messages saved for a run, or [] if there are none or the file is unreadable."""
    path = _log_file(Path(log_dir), run_id)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


@dataclass
class BusMessage:
    from_agent: str
    to_agent: str
    message_type: str
    content: Any
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    run_id: int = 0
    read: bool = False


class AgentBus:
    """In-memory P2P message bus, scoped to a single pipeline run.

    Thread-safe for concurrent sub-agent use (asyncio.Lock guards inbox
    mutations).
    """

    def __init__(
        self,
        project_id: int,
        run_id: int,
        log_dir: str | None = None,
    ) -> None:
        self.project_id = project_id
        self.run_id = run_id
        self._inboxes: dict[str, list[BusMessage]] = defaultdict(list)
        self._all_messages: list[BusMessage] = []
        self._lock = asyncio.Lock()
        self._log_path: Path | None = None
        if log_dir:
            p = Path(log_dir)
            p.mkdir(parents=True, exist_ok=True)
            self._log_path = _log_file(p, run_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        content: Any,
    ) -> None:
        """Post a message to another agent's inbox.

        Args:
            from_agent: Name of the sending agent.
            to_agent:   Name of the recipient agent.
            message_type: A short label, e.g. "detailed_critique" or "test_failure".
            content:    Arbitrary serialisable payload.
        """
        msg = BusMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            run_id=self.run_id,
        )
        async with self._lock:
            self._inboxes[to_agent].append(msg)
            self._all_messages.append(msg)
            self._persist()
        log_structured(
            "agent_bus_send",
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            run_id=self.run_id,
        )

    def receive(self, agent_name: str, unread_only: bool = True) -> list[BusMessage]:
        """Return messages from an agent's inbox.

        Marks returned messages as read by default so they are not
        returned again on a subsequent call.

        Args:
            agent_name:  The agent whose inbox to drain.
            unread_only: If True (default), only return unread messages.

        Returns:
            List of BusMessage objects (may be empty).
        """
        inbox = self._inboxes.get(agent_name, [])
        if unread_only:
            messages = [m for m in inbox if not m.read]
            for m in messages:
                m.read = True
        else:
            messages = list(inbox)
        return messages

    def all_messages(self) -> list[dict]:
        """Return all messages as plain dicts (for timeline logging)."""
        return [asdict(m) for m in self._all_messages]

    def summary(self) -> dict:
        """Return a lightweight summary for timeline entries."""
        return {
            "total_messages": len(self._all_messages),
            "agents_with_inbox": [
                a for a, msgs in self._inboxes.items() if msgs
            ],
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Write all messages to the JSON log (best-effort, never raises)."""
        if not self._log_path:
            return
        try:
            with open(self._log_path, "w", encoding="utf-8") as f:
                json.dump([asdict(m) for m in self._all_messages], f, indent=2)
        except Exception:
            pass
