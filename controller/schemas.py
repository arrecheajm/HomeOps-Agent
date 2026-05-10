"""Validation helpers for collected server health payloads."""

from __future__ import annotations

from typing import Any


def validate_server_health(health: dict[str, Any]) -> None:
    """Raise ValueError if a server health payload has unsafe shapes."""

    _optional_str(health, "schema_version")
    _optional_str(health, "server_id")
    _optional_str(health, "role")
    _optional_str(health, "collected_at")
    _optional_str(health, "hostname")
    _optional_number(health, "uptime_seconds")
    _optional_object(health, "os")
    _optional_object(health, "hardware")
    _optional_object(health, "resources")
    _optional_object(health, "updates")
    _optional_object(health, "docker")
    _optional_object(health, "security")
    _optional_list_of_objects(health, "disk")
    _optional_list_of_objects(health, "services")

    for index, disk in enumerate(health.get("disk") or []):
        _optional_str(disk, "mount", f"disk[{index}]")
        _optional_number(disk, "used_percent", f"disk[{index}]")
        _optional_number(disk, "free_gb", f"disk[{index}]")
        _optional_number(disk, "size_gb", f"disk[{index}]")

    hardware = health.get("hardware")
    if isinstance(hardware, dict):
        _optional_str(hardware, "architecture", "hardware")
        _optional_str(hardware, "cpu_model", "hardware")
        _optional_number(hardware, "memory_total_mb", "hardware")
        _optional_str(hardware, "virtualization", "hardware")

    for index, service in enumerate(health.get("services") or []):
        _optional_str(service, "name", f"services[{index}]")
        _optional_str(service, "state", f"services[{index}]")
        if "enabled" in service and not isinstance(service["enabled"], bool):
            raise ValueError(f"services[{index}].enabled must be a boolean.")

    updates = health.get("updates")
    if isinstance(updates, dict):
        _optional_number(updates, "pending_total", "updates")
        _optional_number(updates, "pending_security", "updates")
        if "reboot_required" in updates and not isinstance(
            updates["reboot_required"], bool
        ):
            raise ValueError("updates.reboot_required must be a boolean.")

    docker = health.get("docker")
    if isinstance(docker, dict):
        if "installed" in docker and not isinstance(docker["installed"], bool):
            raise ValueError("docker.installed must be a boolean.")
        _optional_number(docker, "containers_total", "docker")
        _optional_number(docker, "containers_running", "docker")
        _optional_list_of_objects(docker, "unhealthy", "docker")
        _optional_list_of_objects(docker, "expected_stopped", "docker")

    security = health.get("security")
    if isinstance(security, dict):
        _optional_number(security, "failed_ssh_logins_24h", "security")
        _optional_number(security, "successful_ssh_logins_24h", "security")
        _optional_list_of_strings(security, "last_login_summary", "security")


def _optional_object(
    value: dict[str, Any], key: str, parent: str | None = None
) -> None:
    if key in value and not isinstance(value[key], dict):
        raise ValueError(f"{_name(key, parent)} must be an object.")


def _optional_list_of_objects(
    value: dict[str, Any], key: str, parent: str | None = None
) -> None:
    if key not in value:
        return
    if not isinstance(value[key], list):
        raise ValueError(f"{_name(key, parent)} must be a list.")
    for index, item in enumerate(value[key]):
        if not isinstance(item, dict):
            raise ValueError(f"{_name(key, parent)}[{index}] must be an object.")


def _optional_list_of_strings(
    value: dict[str, Any], key: str, parent: str | None = None
) -> None:
    if key not in value:
        return
    if not isinstance(value[key], list):
        raise ValueError(f"{_name(key, parent)} must be a list.")
    for index, item in enumerate(value[key]):
        if not isinstance(item, str):
            raise ValueError(f"{_name(key, parent)}[{index}] must be a string.")


def _optional_number(
    value: dict[str, Any], key: str, parent: str | None = None
) -> None:
    if key in value and not isinstance(value[key], (int, float)):
        raise ValueError(f"{_name(key, parent)} must be a number.")


def _optional_str(value: dict[str, Any], key: str, parent: str | None = None) -> None:
    if key in value and not isinstance(value[key], str):
        raise ValueError(f"{_name(key, parent)} must be a string.")


def _name(key: str, parent: str | None) -> str:
    if parent:
        return f"{parent}.{key}"
    return key
