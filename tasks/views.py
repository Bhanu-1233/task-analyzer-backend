from __future__ import annotations

import json
from typing import Any, Dict, List

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .scoring import StrategyError, rank_tasks
from .serializers import PayloadError, extract_tasks_and_strategy


def _add_cors_headers(response: JsonResponse) -> JsonResponse:
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def _json_error(message: str, status: int = 400) -> JsonResponse:
    resp = JsonResponse({"detail": message}, status=status)
    return _add_cors_headers(resp)


@csrf_exempt
def analyze_tasks(request: HttpRequest) -> JsonResponse:
    """POST /api/tasks/analyze/

    Accepts:
        {
          "tasks": [...],
          "strategy": "smart_balance" | "fastest_wins" | "high_impact" | "deadline_driven"
        }
    or simply:
        [ ... ]  # list of tasks, default "smart_balance"

    Returns:
        JSON array of ranked tasks with `score` and `explanation`.
    """
    if request.method == "OPTIONS":
        return _add_cors_headers(JsonResponse({}))

    if request.method != "POST":
        return _json_error("Method not allowed", status=405)

    try:
        raw_body = request.body.decode("utf-8") or "{}"
        payload: Any = json.loads(raw_body)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON payload")

    try:
        tasks_raw, strategy = extract_tasks_and_strategy(payload)
        ranked = rank_tasks(tasks_raw, strategy)
    except PayloadError as exc:
        return _json_error(str(exc))
    except StrategyError as exc:
        return _json_error(str(exc))

    resp = JsonResponse(ranked, safe=False)
    return _add_cors_headers(resp)


@csrf_exempt
def suggest_tasks(request: HttpRequest) -> JsonResponse:
    """GET /api/tasks/suggest/

    Query params:
        - strategy: optional, default "smart_balance"
        - tasks: required, JSON array of task objects

    The frontend passes the current client-side tasks as a JSON string in the
    `tasks` query parameter, keeping the backend stateless.
    """
    if request.method == "OPTIONS":
        return _add_cors_headers(JsonResponse({}))

    if request.method != "GET":
        return _json_error("Method not allowed", status=405)

    strategy = (request.GET.get("strategy") or "smart_balance").strip()
    raw_tasks_param = request.GET.get("tasks")

    if not raw_tasks_param:
        return _json_error(
            "No tasks provided. Pass a `tasks` query parameter containing a JSON array.",
            status=400,
        )

    try:
        tasks_raw: Any = json.loads(raw_tasks_param)
    except json.JSONDecodeError:
        return _json_error("`tasks` query parameter must be valid JSON", status=400)

    if not isinstance(tasks_raw, list):
        return _json_error("`tasks` must be a JSON array", status=400)

    try:
        ranked = rank_tasks(tasks_raw, strategy)
    except StrategyError as exc:
        return _json_error(str(exc))

    top_three = ranked[:3]
    resp = JsonResponse(top_three, safe=False)
    return _add_cors_headers(resp)
