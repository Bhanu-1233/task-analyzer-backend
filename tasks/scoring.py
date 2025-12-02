from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


class StrategyError(ValueError):
    """Raised when an unknown strategy is requested."""


@dataclass
class TaskInput:
    id: Optional[Any]
    title: str
    due_date: Optional[date]
    estimated_hours: Optional[float]
    importance: Optional[int]
    dependencies: List[Any]


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _urgency_score(due: Optional[date], today: Optional[date] = None) -> Tuple[float, str]:
    if today is None:
        today = date.today()

    if due is None:
        return 50.0, "no due date (neutral urgency)"

    delta_days = (due - today).days
    if delta_days < 0:
        return 100.0, f"overdue by {-delta_days} day(s)"
    if delta_days == 0:
        return 95.0, "due today"
    if delta_days <= 30:
        score = 30.0 + (30 - delta_days) * (60.0 / 30.0)
        return score, f"due in {delta_days} day(s)"
    return 20.0, f"due in {delta_days} day(s) (low urgency)"


def _importance_score(importance: Optional[int]) -> Tuple[float, str]:
    if importance is None:
        return 50.0, "importance not specified (neutral)"
    imp = _clamp(float(importance), 1.0, 10.0)
    score = imp / 10.0 * 100.0
    return score, f"importance {imp:.0f}/10"


def _effort_score(hours: Optional[float]) -> Tuple[float, str]:
    if hours is None:
        return 50.0, "effort unknown (neutral)"

    h = max(0.0, float(hours))
    if h == 0:
        return 100.0, "trivial effort"
    if h <= 1:
        return 95.0, f"very low effort ({h:.1f}h)"
    if h <= 4:
        score = 95.0 - (h - 1.0) * (35.0 / 3.0)
        return score, f"moderate effort ({h:.1f}h)"
    if h <= 8:
        score = 60.0 - (h - 4.0) * (30.0 / 4.0)
        return score, f"high effort ({h:.1f}h)"
    return 20.0, f"very high effort ({h:.1f}h)"


def _build_graph(tasks: Iterable[TaskInput]) -> Tuple[Dict[Any, List[Any]], Dict[Any, int]]:
    graph: Dict[Any, List[Any]] = {}
    dependents_count: Dict[Any, int] = {}

    for t in tasks:
        if t.id is None:
            continue
        graph.setdefault(t.id, [])
        dependents_count.setdefault(t.id, 0)

    for t in tasks:
        if t.id is None:
            continue
        deps: List[Any] = []
        for dep in t.dependencies:
            if dep in graph:
                deps.append(dep)
                dependents_count[dep] = dependents_count.get(dep, 0) + 1
        graph[t.id] = deps

    return graph, dependents_count


def _detect_cycles(graph: Dict[Any, List[Any]]) -> Set[Any]:
    visited: Set[Any] = set()
    stack: Set[Any] = set()
    in_cycle: Set[Any] = set()

    def visit(node: Any) -> None:
        if node in stack:
            in_cycle.update(stack)
            return
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        for neighbor in graph.get(node, []):
            visit(neighbor)
        stack.remove(node)

    for node in graph:
        if node not in visited:
            visit(node)
    return in_cycle


def _dependency_score(
    task: TaskInput, dependents_count: Dict[Any, int], in_cycle: Set[Any]
) -> Tuple[float, str]:
    if task.id is None:
        return 40.0, "no explicit ID (dependency impact limited)"

    dependents = dependents_count.get(task.id, 0)
    base = 40.0 + min(dependents * 15.0, 45.0)
    explanation = f"unblocks {dependents} other task(s)" if dependents else "no tasks directly depend on this"

    if task.id in in_cycle:
        base *= 0.75
        explanation += ", part of a circular dependency (penalised)"

    return base, explanation


def _compute_score_for_strategy(
    urgency: float,
    importance: float,
    effort: float,
    dependency: float,
    strategy: str,
) -> float:
    strategy = strategy or "smart_balance"

    if strategy == "fastest_wins":
        return 0.60 * effort + 0.25 * importance + 0.15 * urgency
    if strategy == "high_impact":
        return 0.70 * importance + 0.20 * urgency + 0.10 * dependency
    if strategy == "deadline_driven":
        return 0.70 * urgency + 0.20 * importance + 0.10 * dependency
    if strategy == "smart_balance":
        return 0.35 * importance + 0.30 * urgency + 0.20 * dependency + 0.15 * effort

    raise StrategyError(f"Unknown strategy: {strategy}")


def normalise_tasks(raw_tasks: Iterable[dict]) -> List[TaskInput]:
    normalised: List[TaskInput] = []
    for idx, raw in enumerate(raw_tasks, start=1):
        if not isinstance(raw, dict):
            continue
        task_id = raw.get("id", idx)
        title = str(raw.get("title") or "Untitled task").strip() or "Untitled task"
        due_date = _parse_date(raw.get("due_date"))
        est_hours_raw = raw.get("estimated_hours")
        try:
            estimated_hours = float(est_hours_raw) if est_hours_raw is not None else None
        except (TypeError, ValueError):
            estimated_hours = None
        imp_raw = raw.get("importance")
        try:
            importance = int(imp_raw) if imp_raw is not None else None
        except (TypeError, ValueError):
            importance = None
        deps_raw = raw.get("dependencies") or []
        if isinstance(deps_raw, str):
            deps = [d.strip() for d in deps_raw.split(',') if d.strip()]
        elif isinstance(deps_raw, list):
            deps = list(deps_raw)
        else:
            deps = []

        normalised.append(
            TaskInput(
                id=task_id,
                title=title,
                due_date=due_date,
                estimated_hours=estimated_hours,
                importance=importance,
                dependencies=deps,
            )
        )
    return normalised


def rank_tasks(raw_tasks: Iterable[dict], strategy: str) -> List[dict]:
    tasks = normalise_tasks(raw_tasks)
    graph, dependents_count = _build_graph(tasks)
    in_cycle = _detect_cycles(graph)

    results: List[dict] = []
    today = date.today()

    for t in tasks:
        urgency, urg_note = _urgency_score(t.due_date, today=today)
        importance, imp_note = _importance_score(t.importance)
        effort, eff_note = _effort_score(t.estimated_hours)
        dependency, dep_note = _dependency_score(t, dependents_count, in_cycle)

        score = _compute_score_for_strategy(
            urgency=urgency,
            importance=importance,
            effort=effort,
            dependency=dependency,
            strategy=strategy,
        )

        explanation_parts = [
            f"Urgency: {urg_note} (score {urgency:.1f})",
            f"Importance: {imp_note} (score {importance:.1f})",
            f"Effort: {eff_note} (score {effort:.1f})",
            f"Dependencies: {dep_note} (score {dependency:.1f})",
        ]
        explanation = '; '.join(explanation_parts)

        raw: Dict[str, Any] = dict(
            id=t.id,
            title=t.title,
            due_date=t.due_date.isoformat() if t.due_date else None,
            estimated_hours=t.estimated_hours,
            importance=t.importance,
            dependencies=t.dependencies,
        )
        raw["score"] = round(score, 2)
        raw["explanation"] = explanation
        results.append(raw)

    def sort_key(item: dict) -> Tuple[float, float, float]:
        score = float(item.get("score") or 0.0)
        due_str = item.get("due_date") or None
        due = _parse_date(due_str)
        if due is None:
            due_weight = 99999.0
        else:
            due_weight = (due - today).days
        importance_val = item.get("importance") or 0
        return (-score, due_weight, -importance_val)

    results.sort(key=sort_key)
    return results
