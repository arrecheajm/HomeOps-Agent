"""Server inventory loading for HomeOps collection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_REMOTE_HEALTH_COMMAND = (
    "/opt/homeops-agent/server-scripts/common/health_summary.sh"
)

ALLOWED_REMOTE_HEALTH_COMMANDS = (DEFAULT_REMOTE_HEALTH_COMMAND,)


@dataclass(frozen=True)
class ServerInventoryItem:
    server_id: str
    role: str
    host: str
    user: str
    port: int = 22
    enabled: bool = True
    connect_timeout_seconds: int = 10
    command_timeout_seconds: int = 30
    remote_health_command: str = DEFAULT_REMOTE_HEALTH_COMMAND

    @property
    def ssh_target(self) -> str:
        return f"{self.user}@{self.host}"


def load_inventory(path: Path) -> list[ServerInventoryItem]:
    """Load enabled server inventory items from JSON-compatible YAML."""

    if not path.exists():
        raise FileNotFoundError(
            f"Inventory file not found: {path}. Copy config/servers.example.yaml "
            "to config/servers.yaml and edit it for your servers."
        )

    raw = _load_mapping(path)
    servers = raw.get("servers")
    if not isinstance(servers, list):
        raise ValueError("Inventory must contain a top-level 'servers' list.")

    items = [_server_from_mapping(index, value) for index, value in enumerate(servers)]
    return [item for item in items if item.enabled]


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = _load_with_yaml_if_available(text, path)

    if not isinstance(data, dict):
        raise ValueError(f"Inventory root must be an object: {path}")
    return data


def _load_with_yaml_if_available(text: str, path: Path) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ValueError(
            f"{path} is not JSON-compatible YAML and PyYAML is not installed. "
            "Use the JSON-compatible example format or install PyYAML."
        ) from exc

    return yaml.safe_load(text)


def _server_from_mapping(index: int, value: Any) -> ServerInventoryItem:
    if not isinstance(value, dict):
        raise ValueError(f"servers[{index}] must be an object.")

    required = ("server_id", "role", "host", "user")
    missing = [key for key in required if not value.get(key)]
    if missing:
        raise ValueError(f"servers[{index}] is missing required keys: {missing}")

    remote_health_command = str(
        value.get("remote_health_command") or DEFAULT_REMOTE_HEALTH_COMMAND
    )
    if not is_allowed_remote_health_command(remote_health_command):
        raise ValueError(
            f"servers[{index}].remote_health_command is not approved: "
            f"{remote_health_command}"
        )

    return ServerInventoryItem(
        server_id=str(value["server_id"]),
        role=str(value["role"]),
        host=str(value["host"]),
        user=str(value["user"]),
        port=int(value.get("port", 22)),
        enabled=bool(value.get("enabled", True)),
        connect_timeout_seconds=int(value.get("connect_timeout_seconds", 10)),
        command_timeout_seconds=int(value.get("command_timeout_seconds", 30)),
        remote_health_command=remote_health_command,
    )


def is_allowed_remote_health_command(command: str) -> bool:
    """Return whether a configured remote health command is approved for v1."""

    return command in ALLOWED_REMOTE_HEALTH_COMMANDS
