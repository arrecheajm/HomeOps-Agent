"""Fleet collection orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config
from .inventory import ServerInventoryItem
from .normalizer import normalize_server_health
from .ssh_client import RemoteCommandResult, run_remote_command


def create_run_dir(base_dir: Path | None = None, timestamp: str | None = None) -> Path:
    """Create and return a history run directory."""

    root = base_dir or config.RUNS_DIR
    run_dir = root / config.safe_timestamp(timestamp or config.utc_now_iso())
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    return run_dir


def collect_fleet(
    servers: list[ServerInventoryItem], run_dir: Path | None = None
) -> tuple[dict[str, Any], Path]:
    """Collect health JSON from all enabled servers."""

    actual_run_dir = run_dir or create_run_dir()
    (actual_run_dir / "raw").mkdir(parents=True, exist_ok=True)
    collected_at = config.utc_now_iso()
    server_health: list[dict[str, Any]] = []
    collection_errors: list[dict[str, Any]] = []

    for server in servers:
        result = run_remote_command(server)
        _write_raw_result(actual_run_dir, result)

        if result.exit_code != 0:
            collection_errors.append(
                {
                    "server_id": server.server_id,
                    "message": f"Health command exited with code {result.exit_code}.",
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "stderr": _summary(result.stderr),
                }
            )
            continue

        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            collection_errors.append(
                {
                    "server_id": server.server_id,
                    "message": f"Health command returned invalid JSON: {exc}",
                    "exit_code": result.exit_code,
                    "stderr": _summary(result.stderr),
                }
            )
            continue

        if not isinstance(parsed, dict):
            collection_errors.append(
                {
                    "server_id": server.server_id,
                    "message": "Health command returned JSON that was not an object.",
                    "exit_code": result.exit_code,
                }
            )
            continue

        server_health.append(normalize_server_health(server, parsed))

    fleet = {
        "schema_version": "1.0",
        "generated_at": collected_at,
        "servers_checked": len(server_health),
        "servers_failed": len(collection_errors),
        "servers": server_health,
        "findings": [],
        "collection_errors": collection_errors,
    }
    return fleet, actual_run_dir


def save_fleet_health(fleet: dict[str, Any], run_dir: Path) -> Path:
    """Write fleet health JSON into the run directory."""

    path = run_dir / "fleet-health.json"
    path.write_text(json.dumps(fleet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_raw_result(run_dir: Path, result: RemoteCommandResult) -> Path:
    payload = {
        "server_id": result.server_id,
        "command": result.command,
        "exit_code": result.exit_code,
        "duration_seconds": round(result.duration_seconds, 3),
        "timed_out": result.timed_out,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    path = run_dir / "raw" / f"{result.server_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _summary(value: str, limit: int = 500) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3] + "..."
