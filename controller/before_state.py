"""Before-state snapshot generation for rebuildable servers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config, history
from .inventory import ServerInventoryItem


class BeforeStateError(RuntimeError):
    """Raised when a before-state snapshot cannot be captured."""


@dataclass(frozen=True)
class BeforeStateSnapshot:
    payload: dict[str, Any]
    path: Path


def build_before_state_snapshot(
    run: history.RunSummary,
    server: ServerInventoryItem,
    intent: str,
    actions: list[history.ActionSummary] | None = None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a rebuild before-state snapshot for one inventory server."""

    clean_intent = " ".join(str(intent or "").split())
    if not clean_intent:
        raise BeforeStateError("Before-state intent is required.")
    if not server.rebuildable:
        raise BeforeStateError(
            f"Server is not marked rebuildable: {server.server_id}."
        )

    server_state = _server_state(run, server.server_id)
    findings = _server_findings(run, server.server_id)
    collection_errors = _server_collection_errors(run, server.server_id)
    recent_actions = _recent_actions(actions or [], server.server_id)

    return {
        "schema_version": "1.0",
        "generated_at": generated_at or config.utc_now_iso(),
        "snapshot_type": "before_rebuild",
        "intent": clean_intent,
        "server_id": server.server_id,
        "access_profile": server.access_profile,
        "rebuildable": server.rebuildable,
        "source": {
            "run_id": run.run_id,
            "generated_at": run.generated_at,
            "fleet_path": _repo_path(run.fleet_path),
        },
        "server": server_state,
        "findings": findings,
        "collection_errors": collection_errors,
        "recent_actions": recent_actions,
        "rebuild_readiness": _rebuild_readiness(collection_errors),
    }


def write_before_state_snapshot(
    run: history.RunSummary,
    server: ServerInventoryItem,
    intent: str,
    actions: list[history.ActionSummary] | None = None,
    *,
    output_dir: Path | None = None,
    generated_at: str | None = None,
) -> BeforeStateSnapshot:
    """Write a before-state snapshot and return its path."""

    payload = build_before_state_snapshot(
        run,
        server,
        intent,
        actions,
        generated_at=generated_at,
    )
    root = output_dir or config.BEFORE_STATE_DIR
    root.mkdir(parents=True, exist_ok=True)
    base = f"{config.safe_timestamp(payload['generated_at'])}-{server.server_id}"
    path = root / f"{base}.json"
    suffix = 1
    while path.exists():
        path = root / f"{base}-{suffix}.json"
        suffix += 1
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return BeforeStateSnapshot(payload=payload, path=path)


def server_by_id(
    servers: list[ServerInventoryItem], server_id: str
) -> ServerInventoryItem:
    """Return one inventory server by ID."""

    for server in servers:
        if server.server_id == server_id:
            return server
    raise BeforeStateError(f"Enabled server not found in inventory: {server_id}")


def _server_state(run: history.RunSummary, server_id: str) -> dict[str, Any]:
    for server in run.servers:
        if str(server.get("server_id")) == server_id:
            return dict(server)
    raise BeforeStateError(
        f"Server {server_id} was not present in source run {run.run_id}."
    )


def _server_findings(
    run: history.RunSummary, server_id: str
) -> list[dict[str, Any]]:
    return [
        dict(finding)
        for finding in run.findings
        if str(finding.get("server_id")) == server_id
    ]


def _server_collection_errors(
    run: history.RunSummary, server_id: str
) -> list[dict[str, Any]]:
    return [
        dict(error)
        for error in run.collection_errors
        if str(error.get("server_id")) == server_id
    ]


def _recent_actions(
    actions: list[history.ActionSummary], server_id: str, limit: int = 10
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for action in actions:
        if action.server_id != server_id:
            continue
        summaries.append(
            {
                "timestamp": action.timestamp,
                "action_id": action.action_id,
                "status": action.status,
                "risk": action.risk,
                "dry_run": action.dry_run,
                "arguments": action.arguments,
                "approval_source": action.approval_source,
                "exit_code": action.exit_code,
                "record_path": _repo_path(action.record_path),
                "message": action.message,
            }
        )
        if len(summaries) >= limit:
            break
    return summaries


def _rebuild_readiness(collection_errors: list[dict[str, Any]]) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    if collection_errors:
        blocked_reasons.append(
            "Latest source run has collection errors for this server."
        )
    return {
        "eligible_for_rebuild_planning": not blocked_reasons,
        "blocked_reasons": blocked_reasons,
    }


def _repo_path(path: Path) -> str:
    try:
        return str(path.relative_to(config.BASE_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")
