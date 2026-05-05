"""Normalize per-server health JSON into the fleet schema."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .inventory import ServerInventoryItem


def normalize_server_health(
    server: ServerInventoryItem, health: dict[str, Any]
) -> dict[str, Any]:
    """Return a server health object with required identity fields present."""

    normalized = deepcopy(health)
    normalized.setdefault("schema_version", "1.0")
    normalized["server_id"] = str(normalized.get("server_id") or server.server_id)
    normalized["role"] = str(normalized.get("role") or server.role)
    normalized.setdefault("hostname", server.host)
    normalized.setdefault("disk", [])
    normalized.setdefault("services", [])
    normalized.setdefault("updates", {})
    normalized.setdefault("docker", {"installed": False})
    normalized.setdefault("security", {})
    return normalized
