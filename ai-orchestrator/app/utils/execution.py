"""Helper for starting background work from a request handler."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from app.utils.logging import log_structured

# asyncio only keeps a weak reference to a running task. If nobody else
# holds on to it, Python can delete the task halfway through. We keep a
# strong reference here until the task is done.
_running_tasks: set[asyncio.Task] = set()


def start_background(coro: Coroutine[Any, Any, None], name: str) -> asyncio.Task:
    """Start `coro` without waiting for it, and log it if it crashes."""
    task = asyncio.create_task(coro, name=name)
    _running_tasks.add(task)
    task.add_done_callback(_on_done)
    return task


def _on_done(task: asyncio.Task) -> None:
    _running_tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        log_structured("background_task_crashed", task=task.get_name(), error=repr(task.exception()))
