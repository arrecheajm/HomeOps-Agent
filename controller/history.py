"""Run history loading and grouping helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import config, rules


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    generated_at: str
    generated_dt: datetime
    fleet_path: Path
    report_path: Path | None
    servers_checked: int
    servers_failed: int
    counts: dict[str, int]
    findings: list[dict[str, Any]]
    servers: list[dict[str, Any]]
    collection_errors: list[dict[str, Any]]


@dataclass(frozen=True)
class ActionSummary:
    timestamp: str
    timestamp_dt: datetime
    record_path: Path
    server_id: str
    action_id: str
    status: str
    risk: str
    dry_run: bool
    arguments: dict[str, Any]
    approval_source: str
    command: list[str]
    exit_code: int | None
    message: str


def discover_run_summaries(
    runs_dir: Path | None = None, reports_dir: Path | None = None
) -> list[RunSummary]:
    """Load fleet-health summaries from history run directories."""

    root = runs_dir or config.RUNS_DIR
    output_reports_dir = reports_dir or config.GENERATED_REPORTS_DIR
    if not root.exists():
        return []

    summaries: list[RunSummary] = []
    for run_dir in root.iterdir():
        if not run_dir.is_dir():
            continue
        summary = load_run_summary(run_dir, output_reports_dir)
        if summary:
            summaries.append(summary)

    return sorted(summaries, key=lambda run: run.generated_dt, reverse=True)


def discover_action_summaries(
    actions_dir: Path | None = None,
) -> list[ActionSummary]:
    """Load action attempt summaries from action history records."""

    root = actions_dir or config.ACTIONS_DIR
    if not root.exists():
        return []

    summaries: list[ActionSummary] = []
    for path in root.glob("*.json"):
        summary = load_action_summary(path)
        if summary:
            summaries.append(summary)

    return sorted(summaries, key=lambda action: action.timestamp_dt, reverse=True)


def load_action_summary(path: Path) -> ActionSummary | None:
    """Load one action history record."""

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    if not isinstance(record, dict):
        return None

    timestamp = str(record.get("timestamp") or path.stem)
    arguments = record.get("arguments")
    command = record.get("command")
    return ActionSummary(
        timestamp=timestamp,
        timestamp_dt=parse_timestamp(timestamp),
        record_path=path,
        server_id=str(record.get("server_id") or "unknown"),
        action_id=str(record.get("action_id") or "unknown"),
        status=str(record.get("status") or "unknown"),
        risk=str(record.get("risk") or "unknown"),
        dry_run=bool(record.get("dry_run")),
        arguments=arguments if isinstance(arguments, dict) else {},
        approval_source=str(record.get("approval_source") or "unknown"),
        command=[str(part) for part in command] if isinstance(command, list) else [],
        exit_code=_optional_int(record.get("exit_code")),
        message=str(record.get("message") or ""),
    )


def load_run_summary(run_dir: Path, reports_dir: Path) -> RunSummary | None:
    """Load one run summary from a history run directory."""

    fleet_path = run_dir / "fleet-health.json"
    if not fleet_path.exists():
        return None

    try:
        fleet = json.loads(fleet_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    if not isinstance(fleet, dict):
        return None

    generated_at = str(fleet.get("generated_at") or run_dir.name)
    generated_dt = parse_timestamp(generated_at)
    findings = list(fleet.get("findings") or [])
    report_name = f"homeops-report-{config.safe_timestamp(generated_at)}.md"
    report_path = reports_dir / report_name

    return RunSummary(
        run_id=run_dir.name,
        generated_at=generated_at,
        generated_dt=generated_dt,
        fleet_path=fleet_path,
        report_path=report_path if report_path.exists() else None,
        servers_checked=_as_int(fleet.get("servers_checked")),
        servers_failed=_as_int(fleet.get("servers_failed")),
        counts=rules.count_by_severity(findings),
        findings=findings,
        servers=list(fleet.get("servers") or []),
        collection_errors=list(fleet.get("collection_errors") or []),
    )


def group_runs_by_period(
    runs: list[RunSummary], now: datetime | None = None
) -> list[tuple[str, list[RunSummary]]]:
    """Group runs into practical operating periods."""

    if not runs:
        return []

    local_now = _as_local(now or datetime.now().astimezone())
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    grouped: dict[str, list[RunSummary]] = {}
    order: list[str] = []

    for run in sorted(runs, key=lambda item: item.generated_dt, reverse=True):
        local_dt = _as_local(run.generated_dt)
        if local_dt >= today_start:
            label = "Today"
        elif local_dt >= week_start:
            label = "This Week"
        elif local_dt >= month_start:
            label = "Earlier This Month"
        else:
            label = local_dt.strftime("%B %Y")

        if label not in grouped:
            grouped[label] = []
            order.append(label)
        grouped[label].append(run)

    return [(label, grouped[label]) for label in order]


def parse_timestamp(value: str) -> datetime:
    """Parse controller timestamps into timezone-aware datetimes."""

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _as_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).astimezone()
    return value.astimezone()


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
