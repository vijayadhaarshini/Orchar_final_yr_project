import json
import logging
from typing import Any, Dict

logger = logging.getLogger("ai_orchestrator")


def configure_logging() -> None:
    """Configure root logging for the application."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def log_structured(event: str, **kwargs: Any) -> None:
    """Log a structured JSON event for easier debugging."""

    payload: Dict[str, Any] = {"event": event, **kwargs}
    logger.info(json.dumps(payload, default=str))


