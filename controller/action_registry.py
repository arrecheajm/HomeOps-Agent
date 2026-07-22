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
        "action_id": "inspect_storage_devices",
        "risk": "read_only",
        "description": "Report block-device, filesystem, mount, ownership, and HomeOps storage-sentinel metadata without changing storage.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "inspect_docker_container",
        "risk": "approval_required",
        "description": "Inspect one Docker container status, recent logs, and compact config.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "restart_docker_container",
        "risk": "approval_required",
        "description": "Restart one named Docker container.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "replace_watchtower_container",
        "risk": "approval_required",
        "description": "Pull and recreate the Watchtower container with the approved HomeOps options.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "migrate_watchtower_container",
        "risk": "approval_required",
        "description": "Migrate Watchtower from containrrr/watchtower to nickfedor/watchtower.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "retire_disposable_containers",
        "risk": "approval_required",
        "description": "Remove the confirmed disposable File Browser and test database containers plus their named data volumes.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "preflight_monitoring_images",
        "risk": "approval_required",
        "description": "Pull the four immutable monitoring images and validate their health tooling plus the proposed Prometheus configuration without replacing services.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "preflight_mission_control_images",
        "risk": "approval_required",
        "description": "Pull the three immutable Mission Control images and validate architecture, required tooling, container/volume identities, and LAN-port availability without starting the stack.",
        "server_roles": ["container_host"],
        "implemented": True,
        "execution_timeout_seconds": 240,
    },
    {
        "action_id": "provision_mission_control_secrets",
        "risk": "approval_required",
        "description": "Generate or validate protected ntfy and Uptime Kuma credentials without printing them, then retain ignored local recovery copies.",
        "server_roles": ["container_host"],
        "implemented": True,
        "execution_timeout_seconds": 180,
    },
    {
        "action_id": "provision_mission_control_backup_secret",
        "risk": "approval_required",
        "description": "Generate or validate the protected Mission Control backup master key and retain one ignored local recovery copy without printing it.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "backup_mission_control_stack",
        "risk": "approval_required",
        "description": "Stop only the two stateful Mission Control services, create an authenticated encrypted backup of both named volumes, transfer and rotate it on the workstation, then restore healthy service.",
        "server_roles": ["container_host"],
        "implemented": True,
        "execution_timeout_seconds": 420,
    },
    {
        "action_id": "deploy_mission_control_stack",
        "risk": "approval_required",
        "description": "Stage and bootstrap the fixed Mission Control bundle as disposable acceptance state, with automatic removal on failure.",
        "server_roles": ["container_host"],
        "implemented": True,
        "execution_timeout_seconds": 420,
    },
    {
        "action_id": "rollback_mission_control_stack",
        "risk": "approval_required",
        "description": "Remove only the Mission Control acceptance containers and named volumes before they contain retained household state.",
        "server_roles": ["container_host"],
        "implemented": True,
        "execution_timeout_seconds": 180,
    },
    {
        "action_id": "provision_monitoring_secret",
        "risk": "approval_required",
        "description": "Generate or validate the server-side Grafana admin secret without printing it, then copy it to the ignored local recovery path.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "deploy_monitoring_stack",
        "risk": "approval_required",
        "description": "Stage the fixed monitoring bundle, verify the old stack and secret, then cut over with automatic recovery to the old containers on failure.",
        "server_roles": ["container_host"],
        "implemented": True,
        "execution_timeout_seconds": 240,
    },
    {
        "action_id": "repair_monitoring_grafana",
        "risk": "approval_required",
        "description": "Apply the reviewed Grafana startup fixes, synchronize the protected admin password, and verify authentication without replacing the other monitoring containers.",
        "server_roles": ["container_host"],
        "implemented": True,
        "execution_timeout_seconds": 240,
    },
    {
        "action_id": "rollback_monitoring_stack",
        "risk": "approval_required",
        "description": "Stop the HomeOps monitoring stack, restart the preserved old containers, and remove only the new candidate containers and volumes.",
        "server_roles": ["container_host"],
        "implemented": True,
        "execution_timeout_seconds": 180,
    },
    {
        "action_id": "retire_legacy_monitoring_stack",
        "risk": "approval_required",
        "description": "After rollback acceptance, remove only the four stopped legacy monitoring containers and their two old named volumes.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "retire_legacy_monitoring_files",
        "risk": "approval_required",
        "description": "Remove the three verified obsolete monitoring Compose files and their directory after proving the replacement stack remains healthy.",
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
        "description": "Deploy the approved health summary script.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": True,
    },
    {
        "action_id": "deploy_sudoers_profile",
        "risk": "approval_required",
        "description": "Install the approved sudoers profile for the server access profile.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": True,
    },
    {
        "action_id": "apply_security_updates",
        "risk": "approval_required",
        "description": "Apply security updates using the server unattended-upgrades policy.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": True,
    },
    {
        "action_id": "apply_package_updates",
        "risk": "approval_required",
        "description": "Apply normal package upgrades on the container host using apt-get upgrade.",
        "server_roles": ["container_host"],
        "implemented": True,
    },
    {
        "action_id": "reboot_server",
        "risk": "approval_required",
        "description": "Schedule one approved server reboot.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": True,
    },
    {
        "action_id": "run_admin_command",
        "risk": "approval_required",
        "description": "Run one logged root shell command on an experimental or lab server.",
        "server_roles": ["openvpn_server", "ispy_server", "container_host"],
        "implemented": True,
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
