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
    if "server_id" in normalized:
        normalized["reported_server_id"] = str(normalized["server_id"])
    if "role" in normalized:
        normalized["reported_role"] = str(normalized["role"])
    normalized["server_id"] = server.server_id
    normalized["role"] = server.role
    normalized.setdefault("hostname", server.host)
    normalized.setdefault("disk", [])
    normalized.setdefault("services", [])
    normalized.setdefault("updates", {})
    normalized.setdefault("docker", {"installed": False})
    normalized.setdefault("security", {})
    return normalized
