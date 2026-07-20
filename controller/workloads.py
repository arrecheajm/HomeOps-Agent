"""Desired HomeOps workload manifest loading and normalization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VALID_STATES = {"adopt", "redeploy", "planned"}
VALID_STORAGE_CLASSES = {"internal", "external", "mixed"}


def load_workloads(path: Path, server_id: str) -> dict[str, Any]:
    """Load the desired workload manifest for one server."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or not isinstance(payload.get("servers"), dict):
        return {}
    return normalize_workloads(payload["servers"].get(server_id))


def normalize_workloads(value: Any) -> dict[str, Any]:
    """Return an allowlisted and stable desired-workload structure."""

    if not isinstance(value, dict) or not value:
        return {}
    workloads = [
        _workload(item)
        for item in _list(value.get("workloads"))
        if isinstance(item, dict)
    ]
    return {
        "network_scope": _text(value.get("network_scope"), "lan_only"),
        "workloads": sorted(
            workloads,
            key=lambda item: (item["phase"], item["workload_id"]),
        ),
    }


def _workload(value: dict[str, Any]) -> dict[str, Any]:
    state = _text(value.get("state"), "planned")
    if state not in VALID_STATES:
        state = "planned"
    storage_class = _text(value.get("storage_class"), "internal")
    if storage_class not in VALID_STORAGE_CLASSES:
        storage_class = "internal"
    return {
        "workload_id": _text(value.get("workload_id"), "unknown"),
        "phase": _integer(value.get("phase")),
        "state": state,
        "purpose": _text(value.get("purpose"), ""),
        "services": _strings(value.get("services")),
        "current_containers": _strings(value.get("current_containers")),
        "storage_class": storage_class,
        "backup_required": value.get("backup_required") is True,
        "deployment_enabled": value.get("deployment_enabled") is True,
        "prerequisites": _strings(value.get("prerequisites")),
        "acceptance": _strings(value.get("acceptance")),
    }


def _strings(value: Any) -> list[str]:
    return [_text(item, "") for item in _list(value) if _text(item, "")]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, default: str) -> str:
    cleaned = " ".join(str(value or "").split())
    return cleaned or default


def _integer(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
