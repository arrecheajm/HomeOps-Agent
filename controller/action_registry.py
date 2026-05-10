"""Predefined HomeOps action registry."""

from __future__ import annotations

from typing import Any


ACTIONS: tuple[dict[str, Any], ...] = (
    {
        "action_id": "collect_health",
        "risk": "read_only",
        "description": "Collect the combined host health summary.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": False,
    },
    {
        "action_id": "collect_disk",
        "risk": "read_only",
        "description": "Collect disk usage summary.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": False,
    },
    {
        "action_id": "collect_updates",
        "risk": "read_only",
        "description": "Collect package update and reboot-required summary.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": False,
    },
    {
        "action_id": "collect_services",
        "risk": "read_only",
        "description": "Collect approved service status summary.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": False,
    },
    {
        "action_id": "collect_docker",
        "risk": "read_only",
        "description": "Collect Docker service and container status summary.",
        "server_roles": ["container_host"],
        "implemented": False,
    },
    {
        "action_id": "collect_openvpn",
        "risk": "read_only",
        "description": "Collect OpenVPN service and client summary.",
        "server_roles": ["openvpn_server"],
        "implemented": False,
    },
    {
        "action_id": "collect_ispy",
        "risk": "read_only",
        "description": "Collect iSpy service and recording disk summary.",
        "server_roles": ["ispy_server"],
        "implemented": False,
    },
    {
        "action_id": "restart_docker_container",
        "risk": "approval_required",
        "description": "Restart one named Docker container.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "restart_service",
        "risk": "approval_required",
        "description": "Restart one approved system service.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": True,
    },
    {
        "action_id": "deploy_health_script",
        "risk": "approval_required",
        "description": "Deploy the approved read-only health summary script.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": True,
    },
    {
        "action_id": "apply_security_updates",
        "risk": "approval_required",
        "description": "Apply available security updates.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": False,
    },
    {
        "action_id": "reboot_server",
        "risk": "approval_required",
        "description": "Reboot one server.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": False,
    },
)


def list_actions() -> tuple[dict[str, Any], ...]:
    """Return all registered actions."""

    return ACTIONS


def get_action(action_id: str) -> dict[str, Any] | None:
    """Return one registered action definition by ID."""

    for action in ACTIONS:
        if action.get("action_id") == action_id:
            return action
    return None
