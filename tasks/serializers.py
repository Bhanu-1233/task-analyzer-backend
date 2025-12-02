from __future__ import annotations

from typing import Any, Dict, List, Tuple


class PayloadError(ValueError):
    """Raised when the incoming payload is malformed."""


def extract_tasks_and_strategy(payload: Any) -> Tuple[List[dict], str]:
    """Normalise different payload shapes.

    Supports:
    - { "tasks": [...], "strategy": "smart_balance" }
    - [ ... ]  # raw list of tasks, default strategy
    """
    if isinstance(payload, list):
        tasks_raw = payload
        strategy = "smart_balance"
    elif isinstance(payload, dict):
        tasks_raw = payload.get("tasks") or []
        strategy = (payload.get("strategy") or "smart_balance").strip()
    else:
        raise PayloadError("Payload must be a JSON object or array")

    if not isinstance(tasks_raw, list):
        raise PayloadError("`tasks` must be a JSON array of task objects")

    return tasks_raw, strategy
