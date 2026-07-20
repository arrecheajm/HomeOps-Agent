"""Sanitized Docker inventory helpers shared by HomeOps reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_container_classifications(
    path: Path, server_id: str
) -> dict[str, dict[str, str]]:
    """Load local container disposition recommendations for one server."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or not isinstance(payload.get("servers"), dict):
        return {}
    server = payload["servers"].get(server_id)
    if not isinstance(server, dict):
        return {}
    classifications: dict[str, dict[str, str]] = {}
    for name, value in server.items():
        if not isinstance(value, dict):
            continue
        classifications[str(name)] = {
            "classification": _clean_text(value.get("classification"), "unclassified"),
            "rationale": _clean_text(value.get("rationale"), ""),
        }
    return classifications


def normalize_docker_inventory(
    docker: Any,
    classifications: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Return stable, report-safe container inventory entries."""

    if not isinstance(docker, dict) or not isinstance(docker.get("containers"), list):
        return []

    containers: list[dict[str, Any]] = []
    for value in docker["containers"]:
        if not isinstance(value, dict):
            continue
        ports = _ports(value.get("ports"))
        mounts = _mounts(value.get("mounts"))
        network_mode = _clean_text(value.get("network_mode"), "unknown")
        name = _clean_text(value.get("name"), "unknown")
        decision = (classifications or {}).get(name, {})
        containers.append(
            {
                "name": name,
                "image": _clean_text(value.get("image"), "unknown"),
                "state": _clean_text(value.get("state"), "unknown"),
                "health": _clean_text(value.get("health"), "none"),
                "restart_policy": _clean_text(
                    value.get("restart_policy"), "unknown"
                ),
                "network_mode": network_mode,
                "compose_project": _clean_text(value.get("compose_project"), ""),
                "compose_service": _clean_text(value.get("compose_service"), ""),
                "ports": ports,
                "mounts": mounts,
                "exposure": _exposure(network_mode, ports),
                "classification": _clean_text(
                    decision.get("classification"), "unclassified"
                ),
                "classification_rationale": _clean_text(
                    decision.get("rationale"), ""
                ),
            }
        )
    return sorted(containers, key=lambda item: item["name"].lower())


def inventory_collected(docker: Any) -> bool:
    """Return whether the source run explicitly collected detailed inventory."""

    return isinstance(docker, dict) and docker.get("inventory_collected") is True


def port_labels(container: dict[str, Any]) -> list[str]:
    """Format sanitized port bindings for human-facing reports."""

    labels: list[str] = []
    for port in container.get("ports", []):
        if not isinstance(port, dict):
            continue
        container_port = str(port.get("container_port") or "unknown")
        host_port = str(port.get("host_port") or "")
        host_ip = str(port.get("host_ip") or "")
        if host_port:
            labels.append(f"{host_ip or '*'}:{host_port} -> {container_port}")
        else:
            labels.append(f"{container_port} (internal)")
    return labels


def mount_labels(container: dict[str, Any]) -> list[str]:
    """Format sanitized mount paths for human-facing reports."""

    labels: list[str] = []
    for mount in container.get("mounts", []):
        if not isinstance(mount, dict):
            continue
        source = str(mount.get("source") or "unknown")
        destination = str(mount.get("destination") or "unknown")
        access = "ro" if mount.get("read_only") is True else "rw"
        labels.append(f"{source} -> {destination} ({access})")
    return labels


def _ports(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    ports = []
    for item in value:
        if not isinstance(item, dict):
            continue
        ports.append(
            {
                "container_port": _clean_text(item.get("container_port"), "unknown"),
                "host_ip": _clean_text(item.get("host_ip"), ""),
                "host_port": _clean_text(item.get("host_port"), ""),
            }
        )
    return sorted(
        ports,
        key=lambda item: (
            item["container_port"],
            item["host_ip"],
            item["host_port"],
        ),
    )


def _mounts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    mounts = []
    for item in value:
        if not isinstance(item, dict):
            continue
        mounts.append(
            {
                "type": _clean_text(item.get("type"), "unknown"),
                "source": _clean_text(item.get("source"), "unknown"),
                "destination": _clean_text(item.get("destination"), "unknown"),
                "read_only": item.get("read_only") is True,
            }
        )
    return sorted(mounts, key=lambda item: (item["destination"], item["source"]))


def _exposure(network_mode: str, ports: list[dict[str, str]]) -> str:
    if network_mode == "host":
        return "host network"
    if any(port.get("host_port") for port in ports):
        return "published"
    if ports:
        return "internal only"
    return "none reported"


def _clean_text(value: Any, default: str) -> str:
    cleaned = " ".join(str(value or "").split())
    return cleaned or default
