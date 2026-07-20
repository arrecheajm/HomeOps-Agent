"""Sanitized point-in-time evidence used by the container host review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_container_review_evidence(path: Path, server_id: str) -> dict[str, Any]:
    """Load and normalize locally recorded review evidence for one server."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or not isinstance(payload.get("servers"), dict):
        return {}
    return normalize_container_review_evidence(payload["servers"].get(server_id))


def normalize_container_review_evidence(value: Any) -> dict[str, Any]:
    """Return the allowlisted evidence fields consumed by reports."""

    if not isinstance(value, dict) or not value:
        return {}
    storage = _dict(value.get("storage"))
    root = _dict(storage.get("root_filesystem"))
    disk = _dict(storage.get("host_disk"))
    return {
        "observed_at": _text(value.get("observed_at")),
        "method": _text(value.get("method")),
        "sensitive_content_collected": value.get("sensitive_content_collected") is True,
        "storage": {
            "external_device_detected": storage.get("external_device_detected") is True,
            "host_disk": {
                "model": _text(disk.get("model")),
                "size_bytes": _integer(disk.get("size_bytes")),
                "transport": _text(disk.get("transport")),
            },
            "root_filesystem": {
                "source": _text(root.get("source")),
                "filesystem": _text(root.get("filesystem")),
                "size_bytes": _integer(root.get("size_bytes")),
                "used_bytes": _integer(root.get("used_bytes")),
                "available_bytes": _integer(root.get("available_bytes")),
                "used_percent": _integer(root.get("used_percent")),
            },
            "targets": [
                _storage_target(item)
                for item in _list(storage.get("targets"))
                if isinstance(item, dict)
            ],
        },
        "databases": [
            _database(item)
            for item in _list(value.get("databases"))
            if isinstance(item, dict)
        ],
    }


def _storage_target(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": _text(value.get("path")),
        "backing_target": _text(value.get("backing_target")),
        "source": _text(value.get("source")),
        "filesystem": _text(value.get("filesystem")),
        "aggregate_bytes": _integer(value.get("aggregate_bytes")),
        "top_level_directories": _integer(value.get("top_level_directories")),
        "sentinel_present": value.get("sentinel_present") is True,
    }


def _database(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "container": _text(value.get("container")),
        "engine": _text(value.get("engine")),
        "image": _text(value.get("image")),
        "created": _text(value.get("created")),
        "compose_project": _text(value.get("compose_project")),
        "compose_path": _text(value.get("compose_path")),
        "volume": _text(value.get("volume")),
        "volume_bytes": _integer(value.get("volume_bytes")),
        "preservation_required": value.get("preservation_required") is not False,
        "network_peers": sorted(_text(item) for item in _list(value.get("network_peers")) if _text(item)),
        "application_peers": sorted(_text(item) for item in _list(value.get("application_peers")) if _text(item)),
        "query_status": _text(value.get("query_status")),
        "databases": [
            {
                "name": _text(item.get("name")),
                "size_bytes": _integer(item.get("size_bytes")),
            }
            for item in _list(value.get("databases"))
            if isinstance(item, dict)
        ],
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _integer(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
