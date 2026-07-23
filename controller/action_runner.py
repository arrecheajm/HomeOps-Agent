"""Approval-gated action execution for predefined HomeOps actions."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from os.path import expanduser, expandvars
from pathlib import Path
from shlex import quote
from typing import Any

from . import action_registry, approvals, config, policy
from .inventory import (
    ACCESS_PROFILE_EXPERIMENTAL,
    ACCESS_PROFILE_GUARDED,
    ACCESS_PROFILE_LAB,
    DEFAULT_REMOTE_HEALTH_COMMAND,
    ServerInventoryItem,
)
from .ssh_client import build_ssh_base_command


CONTAINER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]*$")
SUDOERS_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*[$]?$")
APPROVED_SERVICE_RESTARTS = {
    "openvpn_server": {
        "openvpnas": "openvpnas.service",
        "openvpnas.service": "openvpnas.service",
    },
    "ispy_server": {
        "AgentDVR": "AgentDVR.service",
        "AgentDVR.service": "AgentDVR.service",
    },
    "container_host": {
        "docker": "docker.service",
        "docker.service": "docker.service",
    },
}
LOCAL_HEALTH_SCRIPT_PATH = (
    config.BASE_DIR / "server-scripts" / "common" / "health_summary.sh"
)
LOCAL_SUDOERS_TEMPLATE_DIR = config.BASE_DIR / "server-scripts" / "sudoers"
SUDOERS_TEMPLATE_NAMES = {
    ACCESS_PROFILE_GUARDED: "guarded.sudoers.template",
    ACCESS_PROFILE_EXPERIMENTAL: "experimental.sudoers.template",
    ACCESS_PROFILE_LAB: "lab.sudoers.template",
}
REMOTE_HEALTH_SCRIPT_PATH = DEFAULT_REMOTE_HEALTH_COMMAND
REMOTE_SUDOERS_PATH = "/etc/sudoers.d/homeops-agent"
REBOOT_DELAY = "+1"
REBOOT_MESSAGE = "HomeOps-approved-reboot"
ADMIN_SHELL_PATH = "/usr/bin/bash"
ADMIN_COMMAND_MAX_LENGTH = 1000
ADMIN_INTENT_MAX_LENGTH = 240
WATCHTOWER_IMAGE = "containrrr/watchtower"
WATCHTOWER_MIGRATION_IMAGE = "nickfedor/watchtower"
WATCHTOWER_NAME = "watchtower"
DISPOSABLE_CONTAINERS = {
    "filebrowser": "filebrowser/filebrowser:latest",
    "mysql57": "mysql:5.7",
    "nonprofit-postgres": "postgres:15",
}
DISPOSABLE_VOLUMES = (
    "dashboards_filebrowser_data",
    "dev-db_mysql_data",
    "nonprofit_postgres_data",
)
MONITORING_IMAGE_REFS = {
    "cadvisor": "ghcr.io/google/cadvisor:v0.57.0@sha256:1742bab953d9d9ab166cba24604a9488efdff7d73dc6d18a087c09a1bcd6cb9d",
    "grafana": "grafana/grafana:13.1.0@sha256:6ea068891652aa6a65ca9065c26b89de939653803c836426970305c11fd00534",
    "node-exporter": "prom/node-exporter:v1.11.1@sha256:fbd8062b4529e166e902bd62cd93de2f48b36d50af942620d419657265bc20b1",
    "prometheus": "prom/prometheus:v3.12.0@sha256:dd4bced05dfaddf23a7ec50f87334993a4149f7fcfbf58456d1c8bafce91cd13",
}
MISSION_CONTROL_IMAGE_REFS = {
    "homepage": "ghcr.io/gethomepage/homepage:v1.13.2@sha256:c881120b024d6a8e2f3c9664efc568984e4352e47df459d6b32e225374c71955",
    "uptime-kuma": "louislam/uptime-kuma:2.4.0@sha256:7e26105b7c8445474a310131590bbfe619e955ed308b5af7e3f0a324bb40ea4d",
    "ntfy": "binwiederhier/ntfy:v2.23.0@sha256:33c067491862f2b302bb5a4571fa0e5a55721ef36d41820979c40533192deaec",
}
MISSION_CONTROL_CONTAINERS = (
    "homeops-mission-control-homepage-1",
    "homeops-mission-control-uptime-kuma-1",
    "homeops-mission-control-ntfy-1",
)
MISSION_CONTROL_VOLUMES = (
    "homeops-mission-control_uptime-kuma-data",
    "homeops-mission-control_ntfy-data",
)
MISSION_CONTROL_PORTS = (8081, 3001, 8082)
MISSION_CONTROL_NTFY_UID = 1000
MISSION_CONTROL_NTFY_GID = 1000
LOCAL_MISSION_CONTROL_DIR = config.BASE_DIR / "stacks" / "mission-control"
LOCAL_MISSION_CONTROL_SECRET_DIR = LOCAL_MISSION_CONTROL_DIR / "secrets"
LOCAL_MISSION_CONTROL_RECOVERY_FILES = (
    LOCAL_MISSION_CONTROL_SECRET_DIR / "uptime_kuma_admin_password",
    LOCAL_MISSION_CONTROL_SECRET_DIR / "ntfy_admin_password",
    LOCAL_MISSION_CONTROL_SECRET_DIR / "ntfy_access_token",
)
LOCAL_MISSION_CONTROL_BACKUP_KEY = (
    LOCAL_MISSION_CONTROL_SECRET_DIR / "backup_key"
)
LOCAL_MISSION_CONTROL_BACKUP_DIR = config.BASE_DIR / "backups" / "mission-control"
LOCAL_MISSION_CONTROL_BACKUP_INCOMING = (
    LOCAL_MISSION_CONTROL_BACKUP_DIR / "mission-control.incoming.enc"
)
LOCAL_MISSION_CONTROL_BACKUP_HMAC_INCOMING = (
    LOCAL_MISSION_CONTROL_BACKUP_DIR / "mission-control.incoming.hmac"
)
LOCAL_MISSION_CONTROL_BACKUP_CURRENT = (
    LOCAL_MISSION_CONTROL_BACKUP_DIR / "mission-control.current.enc"
)
LOCAL_MISSION_CONTROL_BACKUP_HMAC_CURRENT = (
    LOCAL_MISSION_CONTROL_BACKUP_DIR / "mission-control.current.hmac"
)
REMOTE_MISSION_CONTROL_SECRET_DIR = (
    "/home/containerserver/.config/homeops/secrets/mission-control"
)
REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR = (
    f"{REMOTE_MISSION_CONTROL_SECRET_DIR}/ntfy-runtime"
)
REMOTE_MISSION_CONTROL_BACKUP_KEY = (
    f"{REMOTE_MISSION_CONTROL_SECRET_DIR}/backup_key"
)
REMOTE_MISSION_CONTROL_BACKUP_ROOT = (
    "/home/containerserver/.local/share/homeops/backups/mission-control"
)
REMOTE_MISSION_CONTROL_BACKUP_STAGE = (
    f"{REMOTE_MISSION_CONTROL_BACKUP_ROOT}/.stage"
)
REMOTE_MISSION_CONTROL_BACKUP_ENCRYPTED = (
    f"{REMOTE_MISSION_CONTROL_BACKUP_ROOT}/mission-control-backup.enc"
)
REMOTE_MISSION_CONTROL_BACKUP_HMAC = (
    f"{REMOTE_MISSION_CONTROL_BACKUP_ROOT}/mission-control-backup.hmac"
)
REMOTE_MISSION_CONTROL_RESTORE_STAGE = (
    f"{REMOTE_MISSION_CONTROL_BACKUP_ROOT}/.restore-stage"
)
REMOTE_MISSION_CONTROL_SECRET_FILES = {
    "uptime_kuma_admin_password": (
        f"{REMOTE_MISSION_CONTROL_SECRET_DIR}/uptime_kuma_admin_password"
    ),
    "ntfy_admin_password": (
        f"{REMOTE_MISSION_CONTROL_SECRET_DIR}/ntfy_admin_password"
    ),
    "ntfy_admin_password_hash": (
        f"{REMOTE_MISSION_CONTROL_SECRET_DIR}/ntfy_admin_password_hash"
    ),
    "ntfy_service_password_hash": (
        f"{REMOTE_MISSION_CONTROL_SECRET_DIR}/ntfy_service_password_hash"
    ),
    "ntfy_access_token": (
        f"{REMOTE_MISSION_CONTROL_SECRET_DIR}/ntfy_access_token"
    ),
}
REMOTE_MISSION_CONTROL_DIR = (
    "/home/containerserver/.local/share/homeops/stacks/mission-control"
)
REMOTE_MISSION_CONTROL_COMPOSE = f"{REMOTE_MISSION_CONTROL_DIR}/compose.yaml"
MISSION_CONTROL_DEPLOY_FILES = (
    (LOCAL_MISSION_CONTROL_DIR / "compose.yaml", "compose.yaml"),
    (
        LOCAL_MISSION_CONTROL_DIR / "homepage" / "bookmarks.yaml",
        "homepage/bookmarks.yaml",
    ),
    (
        LOCAL_MISSION_CONTROL_DIR / "homepage" / "custom.css",
        "homepage/custom.css",
    ),
    (
        LOCAL_MISSION_CONTROL_DIR / "homepage" / "custom.js",
        "homepage/custom.js",
    ),
    (LOCAL_MISSION_CONTROL_DIR / "homepage" / "docker.yaml", "homepage/docker.yaml"),
    (
        LOCAL_MISSION_CONTROL_DIR / "homepage" / "kubernetes.yaml",
        "homepage/kubernetes.yaml",
    ),
    (
        LOCAL_MISSION_CONTROL_DIR / "homepage" / "proxmox.yaml",
        "homepage/proxmox.yaml",
    ),
    (
        LOCAL_MISSION_CONTROL_DIR / "homepage" / "services.yaml",
        "homepage/services.yaml",
    ),
    (
        LOCAL_MISSION_CONTROL_DIR / "homepage" / "settings.yaml",
        "homepage/settings.yaml",
    ),
    (
        LOCAL_MISSION_CONTROL_DIR / "homepage" / "widgets.yaml",
        "homepage/widgets.yaml",
    ),
    (LOCAL_MISSION_CONTROL_DIR / "ntfy" / "server.yml", "ntfy/server.yml"),
    (
        LOCAL_MISSION_CONTROL_DIR / "uptime-kuma" / "bootstrap.js",
        "uptime-kuma/bootstrap.js",
    ),
    (
        LOCAL_MISSION_CONTROL_DIR / "uptime-kuma" / "bootstrap-contract.js",
        "uptime-kuma/bootstrap-contract.js",
    ),
)
MISSION_CONTROL_HOMEPAGE_REPAIR_FILES = tuple(
    item
    for item in MISSION_CONTROL_DEPLOY_FILES
    if item[1]
    in {
        "homepage/custom.css",
        "homepage/custom.js",
        "homepage/proxmox.yaml",
    }
)
REMOTE_MISSION_CONTROL_HOMEPAGE_REPAIR_STAGE = (
    f"{REMOTE_MISSION_CONTROL_DIR}/.homepage-repair"
)
MISSION_CONTROL_CONTAINER_IMAGES = {
    "homeops-mission-control-homepage-1": MISSION_CONTROL_IMAGE_REFS["homepage"],
    "homeops-mission-control-uptime-kuma-1": MISSION_CONTROL_IMAGE_REFS[
        "uptime-kuma"
    ],
    "homeops-mission-control-ntfy-1": MISSION_CONTROL_IMAGE_REFS["ntfy"],
}
LOCAL_MONITORING_DIR = config.BASE_DIR / "stacks" / "monitoring"
LOCAL_MONITORING_SECRET = (
    LOCAL_MONITORING_DIR / "secrets" / "grafana_admin_password"
)
LOCAL_PROMETHEUS_CONFIG_PATH = LOCAL_MONITORING_DIR / "prometheus" / "prometheus.yml"
LOCAL_PROMETHEUS_RULES_PATH = (
    LOCAL_MONITORING_DIR / "prometheus" / "rules" / "host.rules.yml"
)
REMOTE_PROMETHEUS_PREFLIGHT_CONFIG = "/tmp/homeops-prometheus-preflight.yml"
REMOTE_PROMETHEUS_PREFLIGHT_RULES = "/tmp/homeops-host-rules-preflight.yml"
REMOTE_MONITORING_DIR = "/home/containerserver/.local/share/homeops/stacks/monitoring"
REMOTE_MONITORING_COMPOSE = f"{REMOTE_MONITORING_DIR}/compose.yaml"
REMOTE_MONITORING_SECRET = (
    "/home/containerserver/.config/homeops/secrets/monitoring/"
    "grafana_admin_password"
)
OLD_MONITORING_CONTAINERS = {
    "cadvisor": "gcr.io/cadvisor/cadvisor:latest",
    "monitoring-grafana-1": "grafana/grafana:latest",
    "monitoring-node_exporter-1": "prom/node-exporter:latest",
    "monitoring-prometheus-1": "prom/prometheus:latest",
}
NEW_MONITORING_CONTAINERS = {
    "homeops-monitoring-cadvisor-1": MONITORING_IMAGE_REFS["cadvisor"],
    "homeops-monitoring-grafana-1": MONITORING_IMAGE_REFS["grafana"],
    "homeops-monitoring-node-exporter-1": MONITORING_IMAGE_REFS["node-exporter"],
    "homeops-monitoring-prometheus-1": MONITORING_IMAGE_REFS["prometheus"],
}
NEW_MONITORING_VOLUMES = (
    "homeops-monitoring_grafana-data",
    "homeops-monitoring_prometheus-data",
)
OLD_MONITORING_VOLUMES = (
    "monitoring_grafana-data",
    "monitoring_prometheus-data",
)
LEGACY_MONITORING_DIR = "/home/containerserver/docker_lab/monitoring"
LEGACY_MONITORING_FILES = (
    "docker-compose.yml",
    "prometheus.yml",
    "readme.md",
)
HOMEOPS_STORAGE_MOUNT = "/srv/homeops-storage"
HOMEOPS_STORAGE_SENTINEL = f"{HOMEOPS_STORAGE_MOUNT}/.homeops-storage"
MONITORING_DEPLOY_FILES = (
    (LOCAL_MONITORING_DIR / "compose.yaml", "compose.yaml"),
    (
        LOCAL_MONITORING_DIR / "prometheus" / "prometheus.yml",
        "prometheus/prometheus.yml",
    ),
    (
        LOCAL_MONITORING_DIR / "prometheus" / "rules" / "host.rules.yml",
        "prometheus/rules/host.rules.yml",
    ),
    (
        LOCAL_MONITORING_DIR
        / "grafana"
        / "provisioning"
        / "alerting"
        / "README.md",
        "grafana/provisioning/alerting/README.md",
    ),
    (
        LOCAL_MONITORING_DIR
        / "grafana"
        / "provisioning"
        / "plugins"
        / "README.md",
        "grafana/provisioning/plugins/README.md",
    ),
    (
        LOCAL_MONITORING_DIR
        / "grafana"
        / "provisioning"
        / "datasources"
        / "prometheus.yml",
        "grafana/provisioning/datasources/prometheus.yml",
    ),
    (
        LOCAL_MONITORING_DIR
        / "grafana"
        / "provisioning"
        / "dashboards"
        / "dashboards.yml",
        "grafana/provisioning/dashboards/dashboards.yml",
    ),
    (
        LOCAL_MONITORING_DIR
        / "grafana"
        / "dashboards"
        / "homeops-overview.json",
        "grafana/dashboards/homeops-overview.json",
    ),
)


class ActionError(RuntimeError):
    """Raised when an action request fails safety validation."""


@dataclass(frozen=True)
class ActionAttempt:
    record: dict[str, Any]
    record_path: Path


def run_action(
    action_id: str,
    server_id: str,
    servers: list[ServerInventoryItem],
    arguments: dict[str, Any],
    *,
    approval_text: str | None = None,
    dry_run: bool = False,
    actions_dir: Path | None = None,
    policy_data: dict[str, Any] | None = None,
) -> ActionAttempt:
    """Validate, optionally execute, and record one predefined action."""

    active_policy = policy_data or policy.load_policy()
    action = _action_or_raise(action_id)
    server = _server_or_raise(server_id, servers)
    _validate_action_for_server(action, server)
    commands = build_action_commands(action_id, server, arguments)
    command = commands[0]
    for item in commands:
        _validate_policy(action, item, server, active_policy)

    expected_approval = approvals.approval_phrase(action_id, server_id, arguments)
    risk = str(action.get("risk", "approval_required"))
    approved = dry_run or risk == "read_only"
    approval_source = "not_required" if risk == "read_only" else "dry_run"

    if not approved:
        approved = approvals.approval_matches(
            approval_text,
            action_id,
            server_id,
            arguments,
        )
        approval_source = "cli_approval_text" if approved else "missing_or_invalid"

    if not approved:
        record = _base_record(
            action_id,
            server,
            arguments,
            risk,
            commands,
            approval_source,
            dry_run,
            expected_approval,
        )
        record["status"] = "denied"
        record["message"] = "Approval text did not match the required phrase."
        record_path = write_action_record(record, actions_dir)
        raise ActionError(
            "Action requires exact approval text. "
            f"Expected: {expected_approval}. "
            f"Wrote action record: {record_path}"
        )

    record = _base_record(
        action_id,
        server,
        arguments,
        risk,
        commands,
        approval_source,
        dry_run,
        expected_approval,
    )

    if dry_run:
        record["status"] = "dry_run"
        record["message"] = "Action was validated but not executed."
        record_path = write_action_record(record, actions_dir)
        return ActionAttempt(record=record, record_path=record_path)

    execution_timeout = action.get("execution_timeout_seconds")
    result = _run_commands(
        commands,
        server,
        command_timeout_seconds=(
            int(execution_timeout) if execution_timeout is not None else None
        ),
    )
    record.update(
        {
            "status": "completed" if result["exit_code"] == 0 else "failed",
            "exit_code": result["exit_code"],
            "duration_seconds": result["duration_seconds"],
            "stdout": _summary(result["stdout"]),
            "stderr": _summary(result["stderr"]),
        }
    )
    record_path = write_action_record(record, actions_dir)
    return ActionAttempt(record=record, record_path=record_path)


def build_action_command(
    action_id: str, server: ServerInventoryItem, arguments: dict[str, Any]
) -> list[str]:
    """Build a deterministic SSH command for one implemented action."""

    return build_action_commands(action_id, server, arguments)[0]


def build_action_commands(
    action_id: str, server: ServerInventoryItem, arguments: dict[str, Any]
) -> list[list[str]]:
    """Build deterministic local commands for one implemented action."""

    if action_id == "inspect_storage_devices":
        if arguments:
            raise ActionError(
                "inspect_storage_devices does not accept arguments; its reported "
                "fields and candidate HomeOps mount path are fixed."
            )
        return _inspect_storage_device_commands(server)

    if action_id == "restart_docker_container":
        container = str(arguments.get("container") or "")
        if not CONTAINER_NAME_RE.fullmatch(container):
            raise ActionError(
                "Container name is required and may contain only letters, digits, "
                "periods, underscores, and dashes."
            )
        return [
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command("docker", "restart", container),
            ]
        ]

    if action_id == "inspect_docker_container":
        container = str(arguments.get("container") or "")
        if not CONTAINER_NAME_RE.fullmatch(container):
            raise ActionError(
                "Container name is required and may contain only letters, digits, "
                "periods, underscores, and dashes."
            )
        return [
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command("docker", "ps", "-a", "--filter", f"name={container}"),
            ],
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command("docker", "logs", "--tail", "120", container),
            ],
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command(
                    "docker",
                    "inspect",
                    "--format",
                    "image={{.Config.Image}} restart={{json .HostConfig.RestartPolicy}} cmd={{json .Config.Cmd}} mounts={{json .Mounts}}",
                    container,
                ),
            ],
        ]

    if action_id == "replace_watchtower_container":
        return _watchtower_recreate_commands(server, WATCHTOWER_IMAGE)

    if action_id == "migrate_watchtower_container":
        return _watchtower_recreate_commands(server, WATCHTOWER_MIGRATION_IMAGE)

    if action_id == "retire_disposable_containers":
        if arguments:
            raise ActionError(
                "retire_disposable_containers does not accept arguments; its exact "
                "container and volume bundle is hard-coded."
            )
        return _retire_disposable_container_commands(server)

    if action_id == "preflight_monitoring_images":
        if arguments:
            raise ActionError(
                "preflight_monitoring_images does not accept arguments; its exact "
                "images and validation files are hard-coded."
            )
        return _preflight_monitoring_image_commands(server)

    if action_id == "preflight_mission_control_images":
        if arguments:
            raise ActionError(
                "preflight_mission_control_images does not accept arguments; "
                "its images, identities, tooling, and LAN ports are fixed."
            )
        return _preflight_mission_control_image_commands(server)

    if action_id == "provision_mission_control_secrets":
        if arguments:
            raise ActionError(
                "provision_mission_control_secrets does not accept arguments; "
                "the identities, paths, generation, and recovery copies are fixed."
            )
        return _provision_mission_control_secret_commands(server)

    if action_id == "provision_mission_control_backup_secret":
        if arguments:
            raise ActionError(
                "provision_mission_control_backup_secret does not accept arguments; "
                "the key format, server path, and ignored recovery copy are fixed."
            )
        return _provision_mission_control_backup_secret_commands(server)

    if action_id == "backup_mission_control_stack":
        if arguments:
            raise ActionError(
                "backup_mission_control_stack does not accept arguments; its "
                "volumes, encryption, authentication, destination, and retention are fixed."
            )
        return _backup_mission_control_stack_commands(server)

    if action_id == "restore_mission_control_stack":
        if arguments:
            raise ActionError(
                "restore_mission_control_stack does not accept arguments; its "
                "authenticated source, volumes, rollback snapshots, and verification are fixed."
            )
        return _restore_mission_control_stack_commands(server)

    if action_id == "repair_mission_control_homepage":
        if arguments:
            raise ActionError(
                "repair_mission_control_homepage does not accept arguments; its "
                "required files, container identity, restart, and verification are fixed."
            )
        return _repair_mission_control_homepage_commands(server)

    if action_id == "deploy_mission_control_stack":
        if arguments:
            raise ActionError(
                "deploy_mission_control_stack does not accept arguments; "
                "its files, containers, volumes, bootstrap, and recovery path are fixed."
            )
        return _deploy_mission_control_stack_commands(server)

    if action_id == "rollback_mission_control_stack":
        if arguments:
            raise ActionError(
                "rollback_mission_control_stack does not accept arguments; "
                "it removes only the fixed acceptance containers and volumes."
            )
        return _rollback_mission_control_stack_commands(server)

    if action_id == "provision_monitoring_secret":
        if arguments:
            raise ActionError(
                "provision_monitoring_secret does not accept arguments; the "
                "secret paths and generation method are fixed."
            )
        return _provision_monitoring_secret_commands(server)

    if action_id == "deploy_monitoring_stack":
        if arguments:
            raise ActionError(
                "deploy_monitoring_stack does not accept arguments; its source "
                "files, old containers, new containers, and volumes are fixed."
            )
        return _deploy_monitoring_stack_commands(server)

    if action_id == "repair_monitoring_grafana":
        if arguments:
            raise ActionError(
                "repair_monitoring_grafana does not accept arguments; its "
                "files, containers, checks, and recovery path are fixed."
            )
        return _repair_monitoring_grafana_commands(server)

    if action_id == "rollback_monitoring_stack":
        if arguments:
            raise ActionError(
                "rollback_monitoring_stack does not accept arguments; its old "
                "and new container and volume bundles are fixed."
            )
        return _rollback_monitoring_stack_commands(server)

    if action_id == "retire_legacy_monitoring_stack":
        if arguments:
            raise ActionError(
                "retire_legacy_monitoring_stack does not accept arguments; its "
                "legacy containers and volumes are fixed."
            )
        return _retire_legacy_monitoring_stack_commands(server)

    if action_id == "retire_legacy_monitoring_files":
        if arguments:
            raise ActionError(
                "retire_legacy_monitoring_files does not accept arguments; its "
                "legacy directory and three file names are fixed."
            )
        return _retire_legacy_monitoring_files_commands(server)

    if action_id == "restart_service":
        service = _approved_service_name(server, arguments)
        return [
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command("sudo", "-n", "systemctl", "restart", "--", service),
            ]
        ]

    if action_id == "deploy_health_script":
        return _deploy_health_script_commands(server)

    if action_id == "deploy_sudoers_profile":
        return _deploy_sudoers_profile_commands(server)

    if action_id == "apply_security_updates":
        return [
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command("sudo", "-n", "unattended-upgrade"),
            ]
        ]

    if action_id == "apply_package_updates":
        if server.access_profile != ACCESS_PROFILE_LAB:
            raise ActionError(
                "apply_package_updates is allowed only for lab access profiles. "
                f"Server {server.server_id} is {server.access_profile}."
            )
        return [
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command("sudo", "-n", "apt-get", "update"),
            ],
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command(
                    "sudo",
                    "-n",
                    "env",
                    "DEBIAN_FRONTEND=noninteractive",
                    "apt-get",
                    "-y",
                    "upgrade",
                ),
            ],
        ]

    if action_id == "reboot_server":
        return [
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command(
                    "sudo",
                    "-n",
                    "shutdown",
                    "-r",
                    REBOOT_DELAY,
                    REBOOT_MESSAGE,
                ),
            ]
        ]

    if action_id == "run_admin_command":
        command = _validated_admin_command(server, arguments)
        return [
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command("sudo", "-n", ADMIN_SHELL_PATH, "-lc", command),
            ]
        ]

    raise ActionError(f"Action is not implemented: {action_id}")


def _watchtower_recreate_commands(
    server: ServerInventoryItem, image: str
) -> list[list[str]]:
    return [
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("docker", "pull", image),
        ],
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("docker", "stop", WATCHTOWER_NAME),
        ],
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("docker", "rm", WATCHTOWER_NAME),
        ],
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command(
                "docker",
                "run",
                "-d",
                "--name",
                WATCHTOWER_NAME,
                "--restart",
                "unless-stopped",
                "-v",
                "/var/run/docker.sock:/var/run/docker.sock",
                image,
                "--interval",
                "3600",
                "--label-enable",
                "--cleanup",
            ),
        ],
    ]


def _retire_disposable_container_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    preflight_parts = ["set -eu"]
    for name, image in DISPOSABLE_CONTAINERS.items():
        preflight_parts.append(
            "test \"$(docker inspect --type container --format "
            f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}"
        )
    for volume in DISPOSABLE_VOLUMES:
        preflight_parts.append(
            "test \"$(docker volume inspect --format '{{.Name}}' "
            f"{quote(volume)})\" = {quote(volume)}"
        )
    preflight_parts.append("printf 'retirement_preflight_ok\\n'")

    names = tuple(DISPOSABLE_CONTAINERS)
    verify_script = (
        "set -eu; "
        f"for name in {' '.join(quote(name) for name in names)}; do "
        "if docker container inspect \"$name\" >/dev/null 2>&1; then exit 1; fi; "
        "done; "
        f"for volume in {' '.join(quote(volume) for volume in DISPOSABLE_VOLUMES)}; do "
        "if docker volume inspect \"$volume\" >/dev/null 2>&1; then exit 1; fi; "
        "done; printf 'retirement_verified\\n'"
    )

    return [
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("sh", "-lc", "; ".join(preflight_parts)),
        ],
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("docker", "rm", "--force", "--volumes", "--", *names),
        ],
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("docker", "volume", "rm", "--", *DISPOSABLE_VOLUMES),
        ],
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("sh", "-lc", verify_script),
        ],
    ]


def _preflight_monitoring_image_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    for path in (LOCAL_PROMETHEUS_CONFIG_PATH, LOCAL_PROMETHEUS_RULES_PATH):
        if not path.exists():
            raise ActionError(f"Monitoring preflight file not found: {path}")

    commands: list[list[str]] = []
    for image in MONITORING_IMAGE_REFS.values():
        commands.append(
            build_ssh_base_command(server)
            + [server.ssh_target, _remote_command("docker", "pull", image)]
        )

    for service in ("grafana", "prometheus", "node-exporter"):
        image = MONITORING_IMAGE_REFS[service]
        tool_check = "command -v wget >/dev/null"
        if service == "grafana":
            tool_check += (
                " && command -v curl >/dev/null"
                " && command -v grafana >/dev/null"
            )
        commands.append(
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command(
                    "docker",
                    "run",
                    "--rm",
                    "--entrypoint",
                    "sh",
                    image,
                    "-c",
                    tool_check,
                ),
            ]
        )

    cadvisor_image = MONITORING_IMAGE_REFS["cadvisor"]
    cadvisor_check = (
        "test \"$(docker image inspect --format '{{json .Config.Healthcheck}}' "
        f"{quote(cadvisor_image)})\" != null"
    )
    commands.append(
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", cadvisor_check)]
    )

    commands.append(
        _build_scp_base_command(server)
        + [
            str(LOCAL_PROMETHEUS_CONFIG_PATH),
            f"{server.ssh_target}:{REMOTE_PROMETHEUS_PREFLIGHT_CONFIG}",
        ]
    )
    commands.append(
        _build_scp_base_command(server)
        + [
            str(LOCAL_PROMETHEUS_RULES_PATH),
            f"{server.ssh_target}:{REMOTE_PROMETHEUS_PREFLIGHT_RULES}",
        ]
    )
    prometheus_image = MONITORING_IMAGE_REFS["prometheus"]
    commands.append(
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command(
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "/bin/promtool",
                "-v",
                f"{REMOTE_PROMETHEUS_PREFLIGHT_CONFIG}:/etc/prometheus/prometheus.yml:ro",
                "-v",
                f"{REMOTE_PROMETHEUS_PREFLIGHT_RULES}:/etc/prometheus/rules/host.rules.yml:ro",
                prometheus_image,
                "check",
                "config",
                "/etc/prometheus/prometheus.yml",
            ),
        ]
    )
    commands.append(
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command(
                "rm",
                "-f",
                "--",
                REMOTE_PROMETHEUS_PREFLIGHT_CONFIG,
                REMOTE_PROMETHEUS_PREFLIGHT_RULES,
            ),
        ]
    )
    return commands


def _preflight_mission_control_image_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Validate immutable Mission Control images without starting services."""

    commands: list[list[str]] = []
    for image in MISSION_CONTROL_IMAGE_REFS.values():
        commands.append(
            build_ssh_base_command(server)
            + [server.ssh_target, _remote_command("docker", "pull", image)]
        )

    for service in ("homepage", "uptime-kuma"):
        commands.append(
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command(
                    "docker",
                    "run",
                    "--rm",
                    "--entrypoint",
                    "node",
                    MISSION_CONTROL_IMAGE_REFS[service],
                    "--version",
                ),
            ]
        )

    commands.append(
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command(
                "docker",
                "run",
                "--rm",
                "--read-only",
                "--entrypoint",
                "node",
                MISSION_CONTROL_IMAGE_REFS["uptime-kuma"],
                "-e",
                "require('bcryptjs'); require('socket.io-client')",
            ),
        ]
    )

    commands.append(
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command(
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "sh",
                MISSION_CONTROL_IMAGE_REFS["ntfy"],
                "-c",
                "command -v ntfy >/dev/null && command -v wget >/dev/null "
                "&& command -v grep >/dev/null",
            ),
        ]
    )

    checks = ["set -eu"]
    for image in MISSION_CONTROL_IMAGE_REFS.values():
        checks.append(
            "test \"$(docker image inspect --format '{{.Architecture}}' "
            f"{quote(image)})\" = amd64"
        )
    for name in MISSION_CONTROL_CONTAINERS:
        checks.append(
            f"if docker container inspect {quote(name)} >/dev/null 2>&1; then exit 1; fi"
        )
    for volume in MISSION_CONTROL_VOLUMES:
        checks.append(
            f"if docker volume inspect {quote(volume)} >/dev/null 2>&1; then exit 1; fi"
        )
    for port in MISSION_CONTROL_PORTS:
        checks.append(
            "if ss -H -ltn | awk '{print $4}' | "
            f"grep -Eq '(^|:){port}$'; then exit 1; fi"
        )
    checks.append("printf 'mission_control_image_preflight_ok\\n'")
    commands.append(
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(checks))]
    )
    return commands


def _provision_mission_control_secret_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Create protected Mission Control credentials without logging values."""

    if not LOCAL_MISSION_CONTROL_SECRET_DIR.is_dir():
        raise ActionError(
            "Local Mission Control secret directory not found: "
            f"{LOCAL_MISSION_CONTROL_SECRET_DIR}"
        )

    uptime_password = REMOTE_MISSION_CONTROL_SECRET_FILES[
        "uptime_kuma_admin_password"
    ]
    ntfy_password = REMOTE_MISSION_CONTROL_SECRET_FILES["ntfy_admin_password"]
    ntfy_admin_hash = REMOTE_MISSION_CONTROL_SECRET_FILES[
        "ntfy_admin_password_hash"
    ]
    ntfy_service_hash = REMOTE_MISSION_CONTROL_SECRET_FILES[
        "ntfy_service_password_hash"
    ]
    ntfy_token = REMOTE_MISSION_CONTROL_SECRET_FILES["ntfy_access_token"]
    password_generation = "import secrets; print(secrets.token_urlsafe(32))"
    token_generation = (
        "import secrets,string; alphabet=string.ascii_lowercase+string.digits; "
        "print('tk_'+''.join(secrets.choice(alphabet) for _ in range(29)))"
    )
    bcrypt_generation = (
        "const fs=require('fs');const bcrypt=require('bcryptjs');"
        "const password=fs.readFileSync(0,'utf8').trim();"
        "if(password.length<20)throw new Error('password input is too short');"
        "bcrypt.hash(password,10).then(hash=>{"
        "if(!bcrypt.compareSync(password,hash))throw new Error('bcrypt verification failed');"
        "process.stdout.write(hash+'\\n')})"
        ".catch(error=>{console.error(error.message);process.exit(1)})"
    )
    bcrypt_validation = (
        "const fs=require('fs');const bcrypt=require('bcryptjs');"
        "const password=fs.readFileSync('/secrets/ntfy_admin_password','utf8').trim();"
        "const hash=fs.readFileSync('/secrets/ntfy_admin_password_hash','utf8').trim();"
        "if(!bcrypt.compareSync(password,hash))process.exit(1)"
    )

    script = (
        "set -eu; "
        f"secret_dir={quote(REMOTE_MISSION_CONTROL_SECRET_DIR)}; "
        f"uptime_password={quote(uptime_password)}; "
        f"ntfy_password={quote(ntfy_password)}; "
        f"ntfy_admin_hash={quote(ntfy_admin_hash)}; "
        f"ntfy_service_hash={quote(ntfy_service_hash)}; "
        f"ntfy_token={quote(ntfy_token)}; "
        "install -d -m 0700 \"$secret_dir\"; "
        "test ! -L \"$secret_dir\"; "
        "test \"$(stat -c %a \"$secret_dir\")\" = 700; "
        "test \"$(stat -c %u \"$secret_dir\")\" = \"$(id -u)\"; "
        "for secret in \"$uptime_password\" \"$ntfy_password\"; do "
        "if [ -e \"$secret\" ] || [ -L \"$secret\" ]; then "
        "test -f \"$secret\"; test ! -L \"$secret\"; "
        "else tmp=$(mktemp \"$secret_dir/.password.XXXXXX\"); "
        "trap 'rm -f \"$tmp\"' HUP INT TERM EXIT; "
        f"python3 -c {_shell_single_quote(password_generation)} > \"$tmp\"; "
        "chmod 0600 \"$tmp\"; mv \"$tmp\" \"$secret\"; "
        "trap - HUP INT TERM EXIT; fi; done; "
        "if [ -e \"$ntfy_token\" ] || [ -L \"$ntfy_token\" ]; then "
        "test -f \"$ntfy_token\"; test ! -L \"$ntfy_token\"; "
        "else tmp=$(mktemp \"$secret_dir/.token.XXXXXX\"); "
        "trap 'rm -f \"$tmp\"' HUP INT TERM EXIT; "
        f"python3 -c {_shell_single_quote(token_generation)} > \"$tmp\"; "
        "chmod 0600 \"$tmp\"; mv \"$tmp\" \"$ntfy_token\"; "
        "trap - HUP INT TERM EXIT; fi; "
        "if [ -e \"$ntfy_admin_hash\" ] || [ -L \"$ntfy_admin_hash\" ]; then "
        "test -f \"$ntfy_admin_hash\"; test ! -L \"$ntfy_admin_hash\"; "
        "else tmp=$(mktemp \"$secret_dir/.hash.XXXXXX\"); "
        "trap 'rm -f \"$tmp\"' HUP INT TERM EXIT; "
        f"docker run --rm -i --read-only --entrypoint node {quote(MISSION_CONTROL_IMAGE_REFS['uptime-kuma'])} "
        f"-e {_shell_single_quote(bcrypt_generation)} < \"$ntfy_password\" > \"$tmp\"; "
        "chmod 0600 \"$tmp\"; mv \"$tmp\" \"$ntfy_admin_hash\"; "
        "trap - HUP INT TERM EXIT; fi; "
        "if [ -e \"$ntfy_service_hash\" ] || [ -L \"$ntfy_service_hash\" ]; then "
        "test -f \"$ntfy_service_hash\"; test ! -L \"$ntfy_service_hash\"; "
        "else tmp=$(mktemp \"$secret_dir/.hash.XXXXXX\"); "
        "trap 'rm -f \"$tmp\"' HUP INT TERM EXIT; "
        f"python3 -c {_shell_single_quote(password_generation)} | "
        f"docker run --rm -i --read-only --entrypoint node {quote(MISSION_CONTROL_IMAGE_REFS['uptime-kuma'])} "
        f"-e {_shell_single_quote(bcrypt_generation)} > \"$tmp\"; "
        "chmod 0600 \"$tmp\"; mv \"$tmp\" \"$ntfy_service_hash\"; "
        "trap - HUP INT TERM EXIT; fi; "
        "for secret in \"$uptime_password\" \"$ntfy_password\" \"$ntfy_admin_hash\" \"$ntfy_service_hash\" \"$ntfy_token\"; do "
        "test -s \"$secret\"; test -f \"$secret\"; test ! -L \"$secret\"; "
        "test \"$(stat -c %a \"$secret\")\" = 600; "
        "test \"$(stat -c %u \"$secret\")\" = \"$(id -u)\"; done; "
        "grep -Eq '^tk_[a-z0-9]{29}$' \"$ntfy_token\"; "
        "grep -Eq '^[$]2[aby][$][0-9]{2}[$]' \"$ntfy_admin_hash\"; "
        "grep -Eq '^[$]2[aby][$][0-9]{2}[$]' \"$ntfy_service_hash\"; "
        f"docker run --rm --read-only -v \"$secret_dir:/secrets:ro\" --entrypoint node {quote(MISSION_CONTROL_IMAGE_REFS['uptime-kuma'])} "
        f"-e {_shell_single_quote(bcrypt_validation)}; "
        "printf 'mission_control_secrets_provisioned\\n'"
    )

    commands = [
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", script)]
    ]
    for local_path in LOCAL_MISSION_CONTROL_RECOVERY_FILES:
        remote_path = REMOTE_MISSION_CONTROL_SECRET_FILES[local_path.name]
        commands.append(
            _build_scp_base_command(server)
            + [f"{server.ssh_target}:{remote_path}", str(local_path)]
        )
    return commands


def _provision_mission_control_backup_secret_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Create the protected backup master key and ignored recovery copy."""

    if not LOCAL_MISSION_CONTROL_SECRET_DIR.is_dir():
        raise ActionError(
            "Local Mission Control secret directory not found: "
            f"{LOCAL_MISSION_CONTROL_SECRET_DIR}"
        )
    generation = "import secrets; print(secrets.token_urlsafe(48))"
    script = (
        "set -eu; "
        f"secret_dir={quote(REMOTE_MISSION_CONTROL_SECRET_DIR)}; "
        f"key={quote(REMOTE_MISSION_CONTROL_BACKUP_KEY)}; "
        "install -d -m 0700 \"$secret_dir\"; test ! -L \"$secret_dir\"; "
        "test \"$(stat -c %a \"$secret_dir\")\" = 700; "
        "test \"$(stat -c %u \"$secret_dir\")\" = \"$(id -u)\"; "
        "if [ -e \"$key\" ] || [ -L \"$key\" ]; then "
        "test -f \"$key\"; test ! -L \"$key\"; "
        "else tmp=$(mktemp \"$secret_dir/.backup-key.XXXXXX\"); "
        "trap 'rm -f \"$tmp\"' HUP INT TERM EXIT; "
        f"python3 -c {_shell_single_quote(generation)} > \"$tmp\"; "
        "chmod 0600 \"$tmp\"; mv \"$tmp\" \"$key\"; "
        "trap - HUP INT TERM EXIT; fi; "
        "test -s \"$key\"; test -f \"$key\"; test ! -L \"$key\"; "
        "test \"$(stat -c %a \"$key\")\" = 600; "
        "test \"$(stat -c %u \"$key\")\" = \"$(id -u)\"; "
        "grep -Eq '^[A-Za-z0-9_-]{64}$' \"$key\"; "
        "printf 'mission_control_backup_secret_provisioned\\n'"
    )
    return [
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", script)],
        _build_scp_base_command(server)
        + [
            f"{server.ssh_target}:{REMOTE_MISSION_CONTROL_BACKUP_KEY}",
            str(LOCAL_MISSION_CONTROL_BACKUP_KEY),
        ],
        [
            sys.executable,
            "-m",
            "controller.backup_artifact",
            "validate-key",
            "--path",
            str(LOCAL_MISSION_CONTROL_BACKUP_KEY),
        ],
    ]


def _mission_control_backup_manifest_script() -> str:
    return (
        "import datetime,hashlib,json,pathlib;"
        f"root=pathlib.Path({REMOTE_MISSION_CONTROL_BACKUP_STAGE!r});"
        "exec(\"def item(name,archive):\\n p=root/archive\\n return "
        "{'name':name,'archive':archive,'size':p.stat().st_size,"
        "'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest()}\");"
        "manifest={'schema_version':1,"
        "'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),"
        f"'images':{dict(sorted(MISSION_CONTROL_IMAGE_REFS.items()))!r},"
        "'volumes':[item('homeops-mission-control_uptime-kuma-data','uptime-kuma.tar'),"
        "item('homeops-mission-control_ntfy-data','ntfy.tar')]};"
        "(root/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\\n')"
    )


def _mission_control_backup_hmac_script() -> str:
    return (
        "import hashlib,hmac,pathlib;"
        f"master=pathlib.Path({REMOTE_MISSION_CONTROL_BACKUP_KEY!r}).read_bytes().strip();"
        "key=hmac.new(master,b'homeops-mission-control-backup-hmac-v1',hashlib.sha256).digest();"
        f"source=pathlib.Path({REMOTE_MISSION_CONTROL_BACKUP_ENCRYPTED!r});"
        "digest=hmac.new(key,digestmod=hashlib.sha256);"
        "exec(\"with source.open('rb') as handle:\\n for block in iter(lambda: handle.read(1048576),b''):\\n  digest.update(block)\");"
        f"pathlib.Path({REMOTE_MISSION_CONTROL_BACKUP_HMAC!r}).write_text(digest.hexdigest()+'\\n')"
    )


def _backup_mission_control_stack_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Create, authenticate, transfer, and rotate an encrypted volume backup."""

    if not LOCAL_MISSION_CONTROL_BACKUP_DIR.is_dir():
        raise ActionError(
            "Local Mission Control backup directory not found: "
            f"{LOCAL_MISSION_CONTROL_BACKUP_DIR}"
        )

    manifest_script = _mission_control_backup_manifest_script()
    hmac_script = _mission_control_backup_hmac_script()
    stage_files = tuple(
        f"{REMOTE_MISSION_CONTROL_BACKUP_STAGE}/{name}"
        for name in (
            "uptime-kuma.tar",
            "ntfy.tar",
            "manifest.json",
            "payload.tar",
        )
    )
    cleanup_plaintext = "rm -f -- " + " ".join(quote(path) for path in stage_files)
    restart = (
        "docker start homeops-mission-control-uptime-kuma-1 "
        "homeops-mission-control-ntfy-1 >/dev/null 2>&1 || true; "
        f"{_mission_control_compose_command('up', '-d', '--wait', '--wait-timeout', '180')}"
    )
    recovery = (
        "status=$?; trap - HUP INT TERM EXIT; "
        f"{cleanup_plaintext}; "
        f"rmdir -- {quote(REMOTE_MISSION_CONTROL_BACKUP_STAGE)} >/dev/null 2>&1 || true; "
        "if [ \"$stopped\" = 1 ]; then "
        f"{restart} || status=1; fi; exit \"$status\""
    )
    uptime_image = quote(MISSION_CONTROL_IMAGE_REFS["uptime-kuma"])
    archive_options = (
        "--sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner"
    )
    script = (
        "set -eu; umask 077; stopped=0; "
        f"root={quote(REMOTE_MISSION_CONTROL_BACKUP_ROOT)}; "
        f"stage={quote(REMOTE_MISSION_CONTROL_BACKUP_STAGE)}; "
        f"key={quote(REMOTE_MISSION_CONTROL_BACKUP_KEY)}; "
        f"encrypted={quote(REMOTE_MISSION_CONTROL_BACKUP_ENCRYPTED)}; "
        f"sidecar={quote(REMOTE_MISSION_CONTROL_BACKUP_HMAC)}; "
        "install -d -m 0700 \"$root\"; test ! -L \"$root\"; "
        "test \"$(stat -c %a \"$root\")\" = 700; "
        "test \"$(stat -c %u \"$root\")\" = \"$(id -u)\"; "
        "if [ -L \"$stage\" ]; then exit 1; fi; "
        "if [ -e \"$stage\" ]; then test -d \"$stage\"; "
        f"{cleanup_plaintext}; rmdir -- \"$stage\"; fi; "
        "for output in \"$encrypted\" \"$sidecar\"; do "
        "test ! -L \"$output\"; rm -f -- \"$output\"; done; "
        "test -s \"$key\"; test -f \"$key\"; test ! -L \"$key\"; "
        "test \"$(stat -c %a \"$key\")\" = 600; "
        "test \"$(stat -c %u \"$key\")\" = \"$(id -u)\"; "
        "grep -Eq '^[A-Za-z0-9_-]{64}$' \"$key\"; "
        "openssl version >/dev/null; python3 --version >/dev/null; "
        f"docker image inspect {uptime_image} >/dev/null; "
        "awk 'NR==2 {exit !($4 >= 524288)}' < <(df -Pk \"$root\"); "
        f"test -f {quote(REMOTE_MISSION_CONTROL_COMPOSE)}; "
        + " ".join(
            "test \"$(docker inspect --type container --format "
            f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}; "
            "test \"$(docker inspect --type container --format "
            f"'{{{{.State.Health.Status}}}}' {quote(name)})\" = healthy;"
            for name, image in MISSION_CONTROL_CONTAINER_IMAGES.items()
        )
        + " "
        + " ".join(
            f"docker volume inspect {quote(volume)} >/dev/null;"
            for volume in MISSION_CONTROL_VOLUMES
        )
        + " install -d -m 0700 \"$stage\"; "
        f"trap {_shell_single_quote(recovery)} HUP INT TERM EXIT; "
        "stopped=1; docker stop homeops-mission-control-uptime-kuma-1 "
        "homeops-mission-control-ntfy-1 >/dev/null; "
        "docker run --rm --network none --read-only --user 1000:1000 "
        "--security-opt no-new-privileges:true --cap-drop ALL --pids-limit 64 --memory 128m "
        "-v homeops-mission-control_uptime-kuma-data:/source:ro "
        "-v \"$stage:/backup\" --entrypoint tar "
        f"{uptime_image} {archive_options} -cf /backup/uptime-kuma.tar -C /source .; "
        "docker run --rm --network none --read-only --user 1000:1000 "
        "--security-opt no-new-privileges:true --cap-drop ALL --pids-limit 64 --memory 128m "
        "-v homeops-mission-control_ntfy-data:/source:ro "
        "-v \"$stage:/backup\" --entrypoint tar "
        f"{uptime_image} {archive_options} -cf /backup/ntfy.tar -C /source .; "
        f"python3 -c {_shell_single_quote(manifest_script)}; "
        "docker run --rm --network none --read-only --user 1000:1000 "
        "--security-opt no-new-privileges:true --cap-drop ALL --pids-limit 64 --memory 128m "
        "-v \"$stage:/backup\" --entrypoint tar "
        f"{uptime_image} {archive_options} -cf /backup/payload.tar -C /backup "
        "manifest.json uptime-kuma.tar ntfy.tar; "
        "openssl enc -aes-256-cbc -salt -pbkdf2 -iter 310000 -md sha256 "
        "-pass \"file:$key\" -in \"$stage/payload.tar\" -out \"$encrypted\"; "
        f"python3 -c {_shell_single_quote(hmac_script)}; "
        "chmod 0600 \"$encrypted\" \"$sidecar\"; "
        "test -s \"$encrypted\"; grep -Eq '^[0-9a-f]{64}$' \"$sidecar\"; "
        f"{cleanup_plaintext}; rmdir -- \"$stage\"; "
        f"{restart}; stopped=0; "
        "test \"$(docker inspect --type container --format '{{.State.Health.Status}}' "
        "homeops-mission-control-uptime-kuma-1)\" = healthy; "
        "test \"$(docker inspect --type container --format '{{.State.Health.Status}}' "
        "homeops-mission-control-ntfy-1)\" = healthy; "
        "curl -fsS http://192.168.86.58:3001/status/homeops >/dev/null; "
        "docker exec homeops-mission-control-ntfy-1 ntfy access homeops | "
        "grep -F 'read-write access to topic homeops-alerts' >/dev/null; "
        "trap - HUP INT TERM EXIT; printf 'mission_control_encrypted_backup_ready\\n'"
    )
    cleanup_remote = (
        "set -eu; "
        f"for path in {quote(REMOTE_MISSION_CONTROL_BACKUP_ENCRYPTED)} "
        f"{quote(REMOTE_MISSION_CONTROL_BACKUP_HMAC)}; do "
        "test ! -L \"$path\"; rm -f -- \"$path\"; done; "
        "printf 'mission_control_remote_backup_export_removed\\n'"
    )
    return [
        [
            sys.executable,
            "-m",
            "controller.backup_artifact",
            "prepare",
            "--destination",
            str(LOCAL_MISSION_CONTROL_BACKUP_DIR),
        ],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("bash", "-lc", script)],
        _build_scp_base_command(server)
        + [
            f"{server.ssh_target}:{REMOTE_MISSION_CONTROL_BACKUP_ENCRYPTED}",
            str(LOCAL_MISSION_CONTROL_BACKUP_INCOMING),
        ],
        _build_scp_base_command(server)
        + [
            f"{server.ssh_target}:{REMOTE_MISSION_CONTROL_BACKUP_HMAC}",
            str(LOCAL_MISSION_CONTROL_BACKUP_HMAC_INCOMING),
        ],
        [
            sys.executable,
            "-m",
            "controller.backup_artifact",
            "promote",
            "--destination",
            str(LOCAL_MISSION_CONTROL_BACKUP_DIR),
            "--key",
            str(LOCAL_MISSION_CONTROL_BACKUP_KEY),
        ],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", cleanup_remote)],
    ]


def _mission_control_restore_hmac_script(
    stage_path: str = REMOTE_MISSION_CONTROL_RESTORE_STAGE,
    key_path: str = REMOTE_MISSION_CONTROL_BACKUP_KEY,
) -> str:
    """Return the remote HMAC verification fragment for the restore input."""

    return (
        "import hashlib,hmac,pathlib,re\n"
        f"stage=pathlib.Path({stage_path!r})\n"
        f"master=pathlib.Path({key_path!r}).read_bytes().strip()\n"
        "source=stage/'mission-control.current.enc'\n"
        "expected=(stage/'mission-control.current.hmac').read_text(encoding='ascii').strip()\n"
        "if not re.fullmatch(r'[0-9a-f]{64}',expected):\n"
        " raise ValueError('restore HMAC format is invalid')\n"
        "key=hmac.new(master,b'homeops-mission-control-backup-hmac-v1',hashlib.sha256).digest()\n"
        "digest=hmac.new(key,digestmod=hashlib.sha256)\n"
        "with source.open('rb') as handle:\n"
        " for block in iter(lambda: handle.read(1048576),b''):\n"
        "  digest.update(block)\n"
        "if not hmac.compare_digest(digest.hexdigest(),expected):\n"
        " raise ValueError('restore HMAC verification failed')"
    )


def _mission_control_restore_validation_script(
    stage_path: str = REMOTE_MISSION_CONTROL_RESTORE_STAGE,
) -> str:
    """Return strict payload, manifest, hash, and inner-tar validation."""

    expected_images = dict(sorted(MISSION_CONTROL_IMAGE_REFS.items()))
    expected_volumes = (
        (
            "homeops-mission-control_uptime-kuma-data",
            "uptime-kuma.tar",
        ),
        (
            "homeops-mission-control_ntfy-data",
            "ntfy.tar",
        ),
    )
    return (
        "import datetime,hashlib,json,pathlib,shutil,tarfile\n"
        f"stage=pathlib.Path({stage_path!r})\n"
        "payload=stage/'payload.tar'\n"
        "expected_names={'manifest.json','uptime-kuma.tar','ntfy.tar'}\n"
        "with tarfile.open(payload,'r:') as archive:\n"
        " members=archive.getmembers()\n"
        " by_name={}\n"
        " for member in members:\n"
        "  if member.name in by_name or member.name not in expected_names or not member.isfile():\n"
        "   raise ValueError('unsafe outer backup member')\n"
        "  by_name[member.name]=member\n"
        " if set(by_name)!=expected_names:\n"
        "  raise ValueError('incomplete outer backup payload')\n"
        " for name in sorted(expected_names):\n"
        "  target=stage/name\n"
        "  if target.exists() or target.is_symlink():\n"
        "   raise ValueError('restore output already exists')\n"
        "  source=archive.extractfile(by_name[name])\n"
        "  if source is None:\n"
        "   raise ValueError('backup member is unreadable')\n"
        "  with source,target.open('xb') as output:\n"
        "   shutil.copyfileobj(source,output,1024*1024)\n"
        "manifest=json.loads((stage/'manifest.json').read_text(encoding='utf-8'))\n"
        "if set(manifest)!={'schema_version','created_at','images','volumes'}:\n"
        " raise ValueError('unexpected manifest fields')\n"
        "if manifest['schema_version']!=1:\n"
        " raise ValueError('unsupported manifest schema')\n"
        "created=datetime.datetime.fromisoformat(manifest['created_at'])\n"
        "if created.tzinfo is None:\n"
        " raise ValueError('manifest time is not timezone-aware')\n"
        f"if manifest['images']!={expected_images!r}:\n"
        " raise ValueError('backup image references do not match desired state')\n"
        f"expected_volumes={expected_volumes!r}\n"
        "if not isinstance(manifest['volumes'],list) or len(manifest['volumes'])!=len(expected_volumes):\n"
        " raise ValueError('unexpected backup volume count')\n"
        "for entry,(volume_name,archive_name) in zip(manifest['volumes'],expected_volumes,strict=True):\n"
        " if set(entry)!={'name','archive','size','sha256'} or entry['name']!=volume_name or entry['archive']!=archive_name:\n"
        "  raise ValueError('unexpected backup volume manifest')\n"
        " path=stage/archive_name\n"
        " if type(entry['size']) is not int or entry['size']<=0 or path.stat().st_size!=entry['size']:\n"
        "  raise ValueError('backup archive size mismatch')\n"
        " if not isinstance(entry['sha256'],str) or len(entry['sha256'])!=64 or any(c not in '0123456789abcdef' for c in entry['sha256']):\n"
        "  raise ValueError('backup archive hash format is invalid')\n"
        " with path.open('rb') as source:\n"
        "  actual_hash=hashlib.file_digest(source,'sha256').hexdigest()\n"
        " if actual_hash!=entry['sha256']:\n"
        "  raise ValueError('backup archive hash mismatch')\n"
        " with tarfile.open(path,'r:') as inner:\n"
        "  members=inner.getmembers()\n"
        "  if not members:\n"
        "   raise ValueError('backup archive is empty')\n"
        "  seen=set()\n"
        "  for member in members:\n"
        "   raw=member.name\n"
        "   if '\\\\' in raw:\n"
        "    raise ValueError('unsafe backup path separator')\n"
        "   normalized=raw[2:] if raw.startswith('./') else raw\n"
        "   if normalized in ('','.'):\n"
        "    if not member.isdir():\n"
        "     raise ValueError('unsafe backup root member')\n"
        "    continue\n"
        "   candidate=pathlib.PurePosixPath(normalized)\n"
        "   if candidate.is_absolute() or '..' in candidate.parts or not (member.isdir() or member.isfile()):\n"
        "    raise ValueError('unsafe inner backup member')\n"
        "   canonical=str(candidate)\n"
        "   if canonical in seen:\n"
        "    raise ValueError('duplicate inner backup member')\n"
        "   seen.add(canonical)\n"
        "print('mission_control_restore_payload_validated')"
    )


def _restore_mission_control_stack_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Restore the fixed current backup with automatic live-state rollback."""

    if not LOCAL_MISSION_CONTROL_BACKUP_DIR.is_dir():
        raise ActionError(
            "Local Mission Control backup directory not found: "
            f"{LOCAL_MISSION_CONTROL_BACKUP_DIR}"
        )

    stage_names = (
        "mission-control.current.enc",
        "mission-control.current.hmac",
        "payload.tar",
        "manifest.json",
        "uptime-kuma.tar",
        "ntfy.tar",
        "rollback-uptime-kuma.tar",
        "rollback-ntfy.tar",
    )
    stage_files = tuple(
        f"{REMOTE_MISSION_CONTROL_RESTORE_STAGE}/{name}" for name in stage_names
    )
    cleanup_files = "rm -f -- " + " ".join(quote(path) for path in stage_files)
    prepare = (
        "set -eu; umask 077; "
        f"root={quote(REMOTE_MISSION_CONTROL_BACKUP_ROOT)}; "
        f"stage={quote(REMOTE_MISSION_CONTROL_RESTORE_STAGE)}; "
        "install -d -m 0700 \"$root\"; test ! -L \"$root\"; "
        "test \"$(stat -c %a \"$root\")\" = 700; "
        "test \"$(stat -c %u \"$root\")\" = \"$(id -u)\"; "
        "if [ -L \"$stage\" ]; then exit 1; fi; "
        "if [ -e \"$stage\" ]; then test -d \"$stage\"; "
        f"{cleanup_files}; rmdir -- \"$stage\"; fi; "
        "install -d -m 0700 \"$stage\"; "
        "printf 'mission_control_restore_stage_ready\\n'"
    )

    uptime_image = quote(MISSION_CONTROL_IMAGE_REFS["uptime-kuma"])
    archive_options = "--sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner"
    apply_archive = (
        "apply_archive() { docker run --rm --network none --read-only "
        "--user 1000:1000 --security-opt no-new-privileges:true --cap-drop ALL "
        "--pids-limit 64 --memory 128m -v \"$1:/target\" "
        "-v \"$stage:/restore:ro\" --entrypoint sh "
        f"{uptime_image} -ec "
        + _shell_single_quote(
            "find /target -mindepth 1 -depth -delete; "
            "tar --no-same-owner -xf \"/restore/$1\" -C /target"
        )
        + " sh \"$2\"; }"
    )
    start_and_check = (
        "start_and_check() { "
        f"{_mission_control_compose_command('up', '-d', '--wait', '--wait-timeout', '180')} "
        "&& test \"$(docker inspect --type container --format "
        "'{{.State.Health.Status}}' homeops-mission-control-uptime-kuma-1)\" = healthy "
        "&& test \"$(docker inspect --type container --format "
        "'{{.State.Health.Status}}' homeops-mission-control-ntfy-1)\" = healthy "
        "&& curl -fsS http://192.168.86.58:3001/status/homeops >/dev/null "
        "&& docker exec homeops-mission-control-ntfy-1 ntfy access homeops | "
        "grep -F 'read-write access to topic homeops-alerts' >/dev/null; }"
    )
    cleanup_stage = (
        f"cleanup_stage() {{ {cleanup_files}; "
        f"rmdir -- {quote(REMOTE_MISSION_CONTROL_RESTORE_STAGE)} "
        ">/dev/null 2>&1 || true; }"
    )
    recovery = (
        "status=$?; trap - HUP INT TERM EXIT; set +e; "
        "if [ \"$mutated\" = 1 ]; then "
        "docker stop homeops-mission-control-uptime-kuma-1 "
        "homeops-mission-control-ntfy-1 >/dev/null 2>&1; "
        "apply_archive homeops-mission-control_uptime-kuma-data "
        "rollback-uptime-kuma.tar || status=1; "
        "apply_archive homeops-mission-control_ntfy-data "
        "rollback-ntfy.tar || status=1; "
        "start_and_check || status=1; "
        "elif [ \"$stopped\" = 1 ]; then start_and_check || status=1; fi; "
        "cleanup_stage; exit \"$status\""
    )
    bootstrap_json = (
        "import json,pathlib,sys;"
        f"root=pathlib.Path({REMOTE_MISSION_CONTROL_SECRET_DIR!r});"
        "json.dump({'uptimeKumaAdminPassword':(root/'uptime_kuma_admin_password').read_text().strip(),"
        "'ntfyAccessToken':(root/'ntfy_access_token').read_text().strip()},sys.stdout)"
    )
    bootstrap = (
        f"python3 -c {_shell_single_quote(bootstrap_json)} | "
        "docker exec -i homeops-mission-control-uptime-kuma-1 "
        "node /app/homeops-bootstrap.js"
    )
    restore = (
        "set -eu; umask 077; stopped=0; mutated=0; "
        f"stage={quote(REMOTE_MISSION_CONTROL_RESTORE_STAGE)}; "
        f"key={quote(REMOTE_MISSION_CONTROL_BACKUP_KEY)}; "
        f"{apply_archive}; {start_and_check}; {cleanup_stage}; "
        f"trap {_shell_single_quote(recovery)} HUP INT TERM EXIT; "
        "test -d \"$stage\"; test ! -L \"$stage\"; "
        "test \"$(stat -c %a \"$stage\")\" = 700; "
        "test \"$(stat -c %u \"$stage\")\" = \"$(id -u)\"; "
        "for input in mission-control.current.enc mission-control.current.hmac; do "
        "test -s \"$stage/$input\"; test -f \"$stage/$input\"; "
        "test ! -L \"$stage/$input\"; chmod 0600 \"$stage/$input\"; done; "
        "test -s \"$key\"; test -f \"$key\"; test ! -L \"$key\"; "
        "test \"$(stat -c %a \"$key\")\" = 600; "
        "test \"$(stat -c %u \"$key\")\" = \"$(id -u)\"; "
        "grep -Eq '^[A-Za-z0-9_-]{64}$' \"$key\"; "
        "openssl version >/dev/null; python3 --version >/dev/null; "
        f"docker image inspect {uptime_image} >/dev/null; "
        "docker run --rm --network none --read-only --user 1000:1000 "
        "--security-opt no-new-privileges:true --cap-drop ALL "
        "--pids-limit 16 --memory 32m --entrypoint sh "
        f"{uptime_image} -ec 'command -v find >/dev/null; command -v tar >/dev/null'; "
        "awk 'NR==2 {exit !($4 >= 524288)}' < <(df -Pk \"$stage\"); "
        f"test -f {quote(REMOTE_MISSION_CONTROL_COMPOSE)}; "
        + " ".join(
            "test ! -L "
            f"{quote(f'{REMOTE_MISSION_CONTROL_DIR}/{relative}')}; "
            "test \"$(sha256sum "
            f"{quote(f'{REMOTE_MISSION_CONTROL_DIR}/{relative}')} | "
            f"cut -d ' ' -f 1)\" = "
            f"{quote(hashlib.sha256(source.read_bytes()).hexdigest())};"
            for source, relative in MISSION_CONTROL_DEPLOY_FILES
        )
        + " "
        + " ".join(
            f"test -s {quote(secret)}; test -f {quote(secret)}; "
            f"test ! -L {quote(secret)}; "
            f"test \"$(stat -c %a {quote(secret)})\" = 600; "
            f"test \"$(stat -c %u {quote(secret)})\" = \"$(id -u)\";"
            for secret in REMOTE_MISSION_CONTROL_SECRET_FILES.values()
        )
        + " "
        f"{_mission_control_compose_command('config', '--quiet')}; "
        + " ".join(
            "test \"$(docker inspect --type container --format "
            f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}; "
            "test \"$(docker inspect --type container --format "
            f"'{{{{.State.Health.Status}}}}' {quote(name)})\" = healthy;"
            for name, image in MISSION_CONTROL_CONTAINER_IMAGES.items()
        )
        + " "
        + " ".join(
            f"docker volume inspect {quote(volume)} >/dev/null;"
            for volume in MISSION_CONTROL_VOLUMES
        )
        + " "
        f"python3 -c {_shell_single_quote(_mission_control_restore_hmac_script())}; "
        "openssl enc -d -aes-256-cbc -pbkdf2 -iter 310000 -md sha256 "
        "-pass \"file:$key\" -in \"$stage/mission-control.current.enc\" "
        "-out \"$stage/payload.tar\"; "
        f"python3 -c {_shell_single_quote(_mission_control_restore_validation_script())}; "
        "stopped=1; docker stop homeops-mission-control-uptime-kuma-1 "
        "homeops-mission-control-ntfy-1 >/dev/null; "
        "docker run --rm --network none --read-only --user 1000:1000 "
        "--security-opt no-new-privileges:true --cap-drop ALL --pids-limit 64 --memory 128m "
        "-v homeops-mission-control_uptime-kuma-data:/source:ro "
        "-v \"$stage:/restore\" --entrypoint tar "
        f"{uptime_image} {archive_options} -cf /restore/rollback-uptime-kuma.tar -C /source .; "
        "docker run --rm --network none --read-only --user 1000:1000 "
        "--security-opt no-new-privileges:true --cap-drop ALL --pids-limit 64 --memory 128m "
        "-v homeops-mission-control_ntfy-data:/source:ro "
        "-v \"$stage:/restore\" --entrypoint tar "
        f"{uptime_image} {archive_options} -cf /restore/rollback-ntfy.tar -C /source .; "
        "test -s \"$stage/rollback-uptime-kuma.tar\"; "
        "test -s \"$stage/rollback-ntfy.tar\"; "
        "mutated=1; "
        "apply_archive homeops-mission-control_uptime-kuma-data uptime-kuma.tar; "
        "apply_archive homeops-mission-control_ntfy-data ntfy.tar; "
        f"{_mission_control_compose_command('up', '-d', '--wait', '--wait-timeout', '180')}; "
        f"{bootstrap}; start_and_check; "
        "for binding in "
        "'homeops-mission-control-homepage-1 3000 192.168.86.58:8081' "
        "'homeops-mission-control-uptime-kuma-1 3001 192.168.86.58:3001' "
        "'homeops-mission-control-ntfy-1 8080 192.168.86.58:8082'; do "
        "set -- $binding; test \"$(docker port \"$1\" \"$2/tcp\")\" = \"$3\"; done; "
        "mutated=0; stopped=0; cleanup_stage; trap - HUP INT TERM EXIT; "
        "printf 'mission_control_restore_verified\\n'"
    )
    return [
        [
            sys.executable,
            "-m",
            "controller.backup_artifact",
            "validate-current",
            "--destination",
            str(LOCAL_MISSION_CONTROL_BACKUP_DIR),
            "--key",
            str(LOCAL_MISSION_CONTROL_BACKUP_KEY),
        ],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", prepare)],
        _build_scp_base_command(server)
        + [
            str(LOCAL_MISSION_CONTROL_BACKUP_CURRENT),
            str(LOCAL_MISSION_CONTROL_BACKUP_HMAC_CURRENT),
            f"{server.ssh_target}:{REMOTE_MISSION_CONTROL_RESTORE_STAGE}/",
        ],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("bash", "-lc", restore)],
    ]


def _repair_mission_control_homepage_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Install required read-only Homepage skeleton files and recreate Homepage."""

    for source, _ in MISSION_CONTROL_HOMEPAGE_REPAIR_FILES:
        if not source.is_file():
            raise ActionError(f"Homepage repair file not found: {source}")

    stage = REMOTE_MISSION_CONTROL_HOMEPAGE_REPAIR_STAGE
    stage_files = tuple(
        f"{stage}/{Path(relative).name}"
        for _, relative in MISSION_CONTROL_HOMEPAGE_REPAIR_FILES
    )
    cleanup_stage = (
        "rm -f -- "
        + " ".join(quote(path) for path in stage_files)
        + f"; rmdir -- {quote(stage)} >/dev/null 2>&1 || true"
    )
    preflight = [
        "set -eu",
        f"test -d {quote(REMOTE_MISSION_CONTROL_DIR)}",
        f"test ! -L {quote(REMOTE_MISSION_CONTROL_DIR)}",
        f"test -d {quote(f'{REMOTE_MISSION_CONTROL_DIR}/homepage')}",
        f"test ! -L {quote(f'{REMOTE_MISSION_CONTROL_DIR}/homepage')}",
    ]
    for source, relative in MISSION_CONTROL_DEPLOY_FILES:
        if (source, relative) in MISSION_CONTROL_HOMEPAGE_REPAIR_FILES:
            target = f"{REMOTE_MISSION_CONTROL_DIR}/{relative}"
            preflight.append(
                f"if [ -e {quote(target)} ] || [ -L {quote(target)} ]; then "
                f"test -f {quote(target)}; test ! -L {quote(target)}; fi"
            )
            continue
        expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        target = f"{REMOTE_MISSION_CONTROL_DIR}/{relative}"
        preflight.extend(
            (
                f"test -f {quote(target)}",
                f"test ! -L {quote(target)}",
                "test \"$(sha256sum "
                f"{quote(target)} | cut -d ' ' -f 1)\" = {quote(expected_hash)}",
            )
        )
    preflight.extend(
        (
            _mission_control_compose_command("config", "--quiet"),
            "test \"$(docker inspect --type container --format "
            "'{{.Config.Image}}' homeops-mission-control-homepage-1)\" = "
            + quote(MISSION_CONTROL_IMAGE_REFS["homepage"]),
            "test \"$(docker inspect --type container --format "
            "'{{range .Mounts}}{{.Source}}:{{.Destination}}:{{.RW}}{{end}}' "
            "homeops-mission-control-homepage-1)\" = "
            + quote(
                f"{REMOTE_MISSION_CONTROL_DIR}/homepage:/app/config:false"
            ),
            "test \"$(docker inspect --type container --format "
            "'{{.Config.Image}}' homeops-mission-control-uptime-kuma-1)\" = "
            + quote(MISSION_CONTROL_IMAGE_REFS["uptime-kuma"]),
            "test \"$(docker inspect --type container --format "
            "'{{.State.Health.Status}}' homeops-mission-control-uptime-kuma-1)\" "
            "= healthy",
            "test \"$(docker inspect --type container --format "
            "'{{.Config.Image}}' homeops-mission-control-ntfy-1)\" = "
            + quote(MISSION_CONTROL_IMAGE_REFS["ntfy"]),
            "test \"$(docker inspect --type container --format "
            "'{{.State.Health.Status}}' homeops-mission-control-ntfy-1)\" = healthy",
            f"if [ -L {quote(stage)} ]; then exit 1; fi",
            f"if [ -e {quote(stage)} ]; then test -d {quote(stage)}; "
            f"{cleanup_stage}; fi",
            f"install -d -m 0700 {quote(stage)}",
            "printf 'mission_control_homepage_repair_stage_ready\\n'",
        )
    )
    commands: list[list[str]] = [
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("sh", "-lc", "; ".join(preflight)),
        ]
    ]
    for source, relative in MISSION_CONTROL_HOMEPAGE_REPAIR_FILES:
        commands.append(
            _build_scp_base_command(server)
            + [
                str(source),
                f"{server.ssh_target}:{stage}/{Path(relative).name}",
            ]
        )

    recovery = (
        "status=$?; trap - HUP INT TERM EXIT; "
        f"{cleanup_stage}; "
        f"{_mission_control_compose_command('up', '-d', '--no-deps', 'homepage')} "
        ">/dev/null 2>&1 || status=1; exit \"$status\""
    )
    activate = [
        "set -eu",
        f"trap {_shell_single_quote(recovery)} HUP INT TERM EXIT",
        "kuma_id=$(docker inspect --type container --format '{{.Id}}' "
        "homeops-mission-control-uptime-kuma-1)",
        "ntfy_id=$(docker inspect --type container --format '{{.Id}}' "
        "homeops-mission-control-ntfy-1)",
    ]
    for source, relative in MISSION_CONTROL_HOMEPAGE_REPAIR_FILES:
        expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        candidate = f"{stage}/{Path(relative).name}"
        target = f"{REMOTE_MISSION_CONTROL_DIR}/{relative}"
        activate.extend(
            (
                f"test -f {quote(candidate)}",
                f"test ! -L {quote(candidate)}",
                "test \"$(sha256sum "
                f"{quote(candidate)} | cut -d ' ' -f 1)\" = {quote(expected_hash)}",
                f"install -m 0644 {quote(candidate)} {quote(target)}",
                f"test ! -L {quote(target)}",
                "test \"$(sha256sum "
                f"{quote(target)} | cut -d ' ' -f 1)\" = {quote(expected_hash)}",
            )
        )
    activate.extend(
        (
            cleanup_stage,
            _mission_control_compose_command(
                "up",
                "-d",
                "--no-deps",
                "--force-recreate",
                "--wait",
                "--wait-timeout",
                "180",
                "homepage",
            ),
            "test \"$(docker inspect --type container --format '{{.Id}}' "
            "homeops-mission-control-uptime-kuma-1)\" = \"$kuma_id\"",
            "test \"$(docker inspect --type container --format '{{.Id}}' "
            "homeops-mission-control-ntfy-1)\" = \"$ntfy_id\"",
            "test \"$(docker port homeops-mission-control-homepage-1 3000/tcp)\" "
            "= 192.168.86.58:8081",
            "curl -fsS --max-time 15 "
            "http://192.168.86.58:8081/api/services | grep -F 'Home Operations' "
            ">/dev/null",
            "curl -fsS --max-time 15 "
            "http://192.168.86.58:8081/api/widgets | grep -F 'datetime' >/dev/null",
            "if docker logs homeops-mission-control-homepage-1 2>&1 | "
            "grep -Eq 'Failed to initialize required config|EROFS'; then exit 1; fi",
            "sleep 20",
            "test \"$(docker inspect --type container --format "
            "'{{.State.Health.Status}}' homeops-mission-control-homepage-1)\" = healthy",
            "test \"$(docker inspect --type container --format "
            "'{{.RestartCount}}' homeops-mission-control-homepage-1)\" = 0",
            "trap - HUP INT TERM EXIT",
            "printf 'mission_control_homepage_repaired\\n'",
        )
    )
    commands.append(
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("sh", "-lc", "; ".join(activate)),
        ]
    )
    return commands


def _deploy_mission_control_stack_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Stage and verify the disposable first Mission Control deployment."""

    for source, _ in MISSION_CONTROL_DEPLOY_FILES:
        if not source.exists():
            raise ActionError(f"Mission Control deployment file not found: {source}")

    remote_directories = sorted(
        {
            REMOTE_MISSION_CONTROL_DIR,
            *(
                f"{REMOTE_MISSION_CONTROL_DIR}/{relative.rsplit('/', 1)[0]}"
                for _, relative in MISSION_CONTROL_DEPLOY_FILES
                if "/" in relative
            ),
        }
    )
    directory_preflight = (
        "set -eu; "
        + "; ".join(
            f"if [ -L {quote(path)} ]; then exit 1; fi"
            for path in remote_directories
        )
        + "; "
        + _remote_command("install", "-d", "-m", "0755", *remote_directories)
        + "; printf 'mission_control_directories_ready\\n'"
    )
    commands: list[list[str]] = [
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("sh", "-lc", directory_preflight),
        ]
    ]
    for source, relative in MISSION_CONTROL_DEPLOY_FILES:
        commands.append(
            _build_scp_base_command(server)
            + [
                str(source),
                f"{server.ssh_target}:{REMOTE_MISSION_CONTROL_DIR}/{relative}",
            ]
        )

    preflight = [
        "set -eu",
        f"test ! -L {quote(REMOTE_MISSION_CONTROL_DIR)}",
        f"test \"$(id -u)\" = {MISSION_CONTROL_NTFY_UID}",
        f"test \"$(id -g)\" = {MISSION_CONTROL_NTFY_GID}",
        "if [ -e "
        f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)} ] || [ -L "
        f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)} ]; then exit 1; fi",
    ]
    for remote_secret in REMOTE_MISSION_CONTROL_SECRET_FILES.values():
        preflight.extend(
            (
                f"test -s {quote(remote_secret)}",
                f"test -f {quote(remote_secret)}",
                f"test ! -L {quote(remote_secret)}",
                f"test \"$(stat -c %a {quote(remote_secret)})\" = 600",
                f"test \"$(stat -c %u {quote(remote_secret)})\" = \"$(id -u)\"",
            )
        )
    for image in MISSION_CONTROL_IMAGE_REFS.values():
        preflight.append(f"docker image inspect {quote(image)} >/dev/null")
    for name in MISSION_CONTROL_CONTAINERS:
        preflight.append(
            f"if docker container inspect {quote(name)} >/dev/null 2>&1; then exit 1; fi"
        )
    for volume in MISSION_CONTROL_VOLUMES:
        preflight.append(
            f"if docker volume inspect {quote(volume)} >/dev/null 2>&1; then exit 1; fi"
        )
    for port in MISSION_CONTROL_PORTS:
        preflight.append(
            "if ss -H -ltn | awk '{print $4}' | "
            f"grep -Eq '(^|:){port}$'; then exit 1; fi"
        )
    for source, relative in MISSION_CONTROL_DEPLOY_FILES:
        expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        remote_path = f"{REMOTE_MISSION_CONTROL_DIR}/{relative}"
        preflight.extend(
            (
                f"test ! -L {quote(remote_path)}",
                "test \"$(sha256sum "
                f"{quote(remote_path)} | cut -d ' ' -f 1)\" = {quote(expected_hash)}",
            )
        )
    bcrypt_validation = (
        "const fs=require('fs');const bcrypt=require('bcryptjs');"
        "const password=fs.readFileSync('/secrets/ntfy_admin_password','utf8').trim();"
        "const hash=fs.readFileSync('/secrets/ntfy_admin_password_hash','utf8').trim();"
        "if(!bcrypt.compareSync(password,hash))process.exit(1)"
    )
    preflight.extend(
        (
            "grep -Eq '^tk_[a-z0-9]{29}$' "
            + quote(REMOTE_MISSION_CONTROL_SECRET_FILES["ntfy_access_token"]),
            "grep -Eq '^[$]2[aby][$][0-9]{2}[$]' "
            + quote(
                REMOTE_MISSION_CONTROL_SECRET_FILES["ntfy_admin_password_hash"]
            ),
            "grep -Eq '^[$]2[aby][$][0-9]{2}[$]' "
            + quote(
                REMOTE_MISSION_CONTROL_SECRET_FILES["ntfy_service_password_hash"]
            ),
            "docker run --rm --read-only "
            f"-v {quote(REMOTE_MISSION_CONTROL_SECRET_DIR)}:/secrets:ro "
            "--entrypoint node "
            f"{quote(MISSION_CONTROL_IMAGE_REFS['uptime-kuma'])} "
            f"-e {_shell_single_quote(bcrypt_validation)}",
            _mission_control_compose_command("config", "--quiet"),
            "printf 'mission_control_deploy_preflight_ok\\n'",
        )
    )
    commands.append(
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(preflight))]
    )

    bootstrap_json = (
        "import json,pathlib,sys;"
        f"root=pathlib.Path({REMOTE_MISSION_CONTROL_SECRET_DIR!r});"
        "json.dump({'uptimeKumaAdminPassword':(root/'uptime_kuma_admin_password').read_text().strip(),"
        "'ntfyAccessToken':(root/'ntfy_access_token').read_text().strip()},sys.stdout)"
    )
    bootstrap = (
        f"python3 -c {_shell_single_quote(bootstrap_json)} | "
        "docker exec -i homeops-mission-control-uptime-kuma-1 "
        "node /app/homeops-bootstrap.js"
    )
    ntfy_probe = (
        "import pathlib,urllib.error,urllib.request;"
        f"token=pathlib.Path({REMOTE_MISSION_CONTROL_SECRET_FILES['ntfy_access_token']!r}).read_text().strip();"
        "base='http://127.0.0.1:8082/';"
        "exec(\"def post(topic,auth=None):\\n"
        " h={'Authorization':'Bearer '+auth} if auth else {}\\n"
        " r=urllib.request.Request(base+topic,data=b'HomeOps acceptance check',headers=h,method='POST')\\n"
        " try:\\n  return urllib.request.urlopen(r,timeout=10).status\\n"
        " except urllib.error.HTTPError as e:\\n  return e.code\");"
        "assert post('homeops-alerts') in (401,403);"
        "assert post('homeops-alerts',token)==200;"
        "assert post('homeops-not-authorized',token)==403"
    )
    ntfy_probe_lan = ntfy_probe.replace(
        "http://127.0.0.1:8082/", "http://192.168.86.58:8082/"
    )
    recovery = (
        "status=$?; trap - HUP INT TERM EXIT; "
        f"{_mission_control_compose_command('down', '--volumes')} >/dev/null 2>&1 || true; "
        "rm -f -- "
        f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)}/ntfy_admin_password_hash "
        f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)}/ntfy_service_password_hash "
        f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)}/ntfy_access_token; "
        f"rmdir -- {quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)} "
        ">/dev/null 2>&1 || true; "
        "exit \"$status\""
    )
    deploy = (
        "set -eu; "
        f"trap {_shell_single_quote(recovery)} HUP INT TERM EXIT; "
        f"install -d -m 0700 {quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)}; "
        "for name in ntfy_admin_password_hash ntfy_service_password_hash "
        "ntfy_access_token; do "
        f"install -m 0600 {quote(REMOTE_MISSION_CONTROL_SECRET_DIR)}/\"$name\" "
        f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)}/\"$name\"; done; "
        "HOMEOPS_LAN_IP=127.0.0.1 "
        f"{_mission_control_compose_command('create')}; "
        "docker run --rm --network none --read-only "
        "--security-opt no-new-privileges:true --cap-drop ALL "
        "--pids-limit 32 --memory 64m "
        "-v homeops-mission-control_ntfy-data:/var/lib/ntfy "
        f"--entrypoint chmod {quote(MISSION_CONTROL_IMAGE_REFS['ntfy'])} "
        "0700 /var/lib/ntfy; "
        "docker run --rm --network none --read-only "
        "--security-opt no-new-privileges:true --cap-drop ALL --cap-add CHOWN "
        "--pids-limit 32 --memory 64m "
        "-v homeops-mission-control_ntfy-data:/var/lib/ntfy "
        f"--entrypoint chown {quote(MISSION_CONTROL_IMAGE_REFS['ntfy'])} "
        f"{MISSION_CONTROL_NTFY_UID}:{MISSION_CONTROL_NTFY_GID} /var/lib/ntfy; "
        "HOMEOPS_LAN_IP=127.0.0.1 "
        f"{_mission_control_compose_command('up', '-d', '--wait', '--wait-timeout', '180')}; "
        f"{bootstrap}; "
        f"python3 -c {_shell_single_quote(ntfy_probe)}; "
        f"{_mission_control_compose_command('up', '-d', '--wait', '--wait-timeout', '180')}; "
        "trap - HUP INT TERM EXIT; "
        "printf 'mission_control_acceptance_deployed\\n'"
    )
    commands.append(
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", deploy)]
    )

    verify = ["set -eu", f"trap {_shell_single_quote(recovery)} HUP INT TERM EXIT"]
    for name, image in MISSION_CONTROL_CONTAINER_IMAGES.items():
        verify.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = true",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Health.Status}}}}' {quote(name)})\" = healthy",
            )
        )
    verify.append(
        "test \"$(docker inspect --type container --format "
        "'{{.Config.User}}' homeops-mission-control-ntfy-1)\" = 1000:1000"
    )
    verify.append(
        "test \"$(docker inspect --type container --format "
        "'{{.Config.User}}' homeops-mission-control-uptime-kuma-1)\" = 1000:1000"
    )
    verify.append(
        "docker inspect --type container --format "
        "'{{range .Config.Env}}{{println .}}{{end}}' "
        "homeops-mission-control-uptime-kuma-1 | "
        "grep -Fx UPTIME_KUMA_DB_TYPE=sqlite"
    )
    verify.append(
        "docker exec homeops-mission-control-ntfy-1 sh -ec "
        + _shell_single_quote(
            "test \"$(id -u)\" = 1000; test \"$(id -g)\" = 1000; "
            "test -w /var/lib/ntfy"
        )
    )
    for volume in MISSION_CONTROL_VOLUMES:
        verify.append(f"docker volume inspect {quote(volume)} >/dev/null")
    verify.extend(
        (
            "test \"$(stat -c %a "
            f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)})\" = 700",
            "test \"$(stat -c %u "
            f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)})\" = \"$(id -u)\"",
        )
    )
    for name in (
        "ntfy_admin_password_hash",
        "ntfy_service_password_hash",
        "ntfy_access_token",
    ):
        runtime_secret = f"{REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR}/{name}"
        verify.extend(
            (
                f"test -s {quote(runtime_secret)}",
                f"test ! -L {quote(runtime_secret)}",
                f"test \"$(stat -c %a {quote(runtime_secret)})\" = 600",
                f"test \"$(stat -c %u {quote(runtime_secret)})\" = \"$(id -u)\"",
            )
        )
    for name, container_port, host_port in (
        ("homeops-mission-control-homepage-1", 3000, 8081),
        ("homeops-mission-control-uptime-kuma-1", 3001, 3001),
        ("homeops-mission-control-ntfy-1", 8080, 8082),
    ):
        verify.append(
            f"test \"$(docker port {quote(name)} {container_port}/tcp)\" = "
            f"192.168.86.58:{host_port}"
        )
    verify.extend(
        (
            "curl -fsS --max-time 15 "
            "http://192.168.86.58:8081/api/services | grep -F 'Home Operations' "
            ">/dev/null",
            "curl -fsS --max-time 15 "
            "http://192.168.86.58:8081/api/widgets | grep -F 'datetime' >/dev/null",
            "if docker logs homeops-mission-control-homepage-1 2>&1 | "
            "grep -Eq 'Failed to initialize required config|EROFS'; then exit 1; fi",
            bootstrap,
            f"python3 -c {_shell_single_quote(ntfy_probe_lan)}",
            "trap - HUP INT TERM EXIT",
            "printf 'mission_control_acceptance_verified\\n'",
        )
    )
    commands.append(
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(verify))]
    )
    return commands


def _rollback_mission_control_stack_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Remove only the still-disposable Mission Control acceptance state."""

    preflight = ["set -eu", f"test -f {quote(REMOTE_MISSION_CONTROL_COMPOSE)}"]
    for name, image in MISSION_CONTROL_CONTAINER_IMAGES.items():
        preflight.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = true",
            )
        )
    for volume in MISSION_CONTROL_VOLUMES:
        preflight.append(f"docker volume inspect {quote(volume)} >/dev/null")
    preflight.append("printf 'mission_control_rollback_preflight_ok\\n'")

    rollback = (
        "set -eu; "
        f"{_mission_control_compose_command('down', '--volumes')}; "
        "rm -f -- "
        f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)}/ntfy_admin_password_hash "
        f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)}/ntfy_service_password_hash "
        f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)}/ntfy_access_token; "
        f"rmdir -- {quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)}; "
        "printf 'mission_control_acceptance_rolled_back\\n'"
    )
    verify = ["set -eu"]
    for name in MISSION_CONTROL_CONTAINERS:
        verify.append(
            f"if docker container inspect {quote(name)} >/dev/null 2>&1; then exit 1; fi"
        )
    for volume in MISSION_CONTROL_VOLUMES:
        verify.append(
            f"if docker volume inspect {quote(volume)} >/dev/null 2>&1; then exit 1; fi"
        )
    verify.append(
        "if [ -e "
        f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)} ] || [ -L "
        f"{quote(REMOTE_MISSION_CONTROL_NTFY_RUNTIME_SECRET_DIR)} ]; then exit 1; fi"
    )
    verify.append("printf 'mission_control_rollback_verified\\n'")
    return [
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(preflight))],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", rollback)],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(verify))],
    ]


def _deploy_monitoring_stack_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Build the fixed, recoverable monitoring cutover command sequence."""

    for source, _ in MONITORING_DEPLOY_FILES:
        if not source.exists():
            raise ActionError(f"Monitoring deployment file not found: {source}")

    remote_directories = sorted(
        {
            REMOTE_MONITORING_DIR,
            *(f"{REMOTE_MONITORING_DIR}/{relative.rsplit('/', 1)[0]}"
              for _, relative in MONITORING_DEPLOY_FILES
              if "/" in relative),
        }
    )
    commands: list[list[str]] = [
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("install", "-d", "-m", "0755", *remote_directories),
        ]
    ]

    for source, relative in MONITORING_DEPLOY_FILES:
        commands.append(
            _build_scp_base_command(server)
            + [
                str(source),
                f"{server.ssh_target}:{REMOTE_MONITORING_DIR}/{relative}",
            ]
        )

    preflight_parts = ["set -eu"]
    preflight_parts.extend(
        (
            f"test -s {quote(REMOTE_MONITORING_SECRET)}",
            f"test ! -L {quote(REMOTE_MONITORING_SECRET)}",
            "test \"$(stat -c %a "
            f"{quote(REMOTE_MONITORING_SECRET)})\" = 600",
            "test \"$(stat -c %u "
            f"{quote(REMOTE_MONITORING_SECRET)})\" = \"$(id -u)\"",
        )
    )
    for name, image in OLD_MONITORING_CONTAINERS.items():
        preflight_parts.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = true",
            )
        )
    for name in NEW_MONITORING_CONTAINERS:
        preflight_parts.append(
            f"if docker container inspect {quote(name)} >/dev/null 2>&1; then exit 1; fi"
        )
    for volume in NEW_MONITORING_VOLUMES:
        preflight_parts.append(
            f"if docker volume inspect {quote(volume)} >/dev/null 2>&1; then exit 1; fi"
        )
    for image in MONITORING_IMAGE_REFS.values():
        preflight_parts.append(
            f"docker image inspect {quote(image)} >/dev/null"
        )
    for source, relative in MONITORING_DEPLOY_FILES:
        expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        remote_path = f"{REMOTE_MONITORING_DIR}/{relative}"
        preflight_parts.append(
            "test \"$(sha256sum "
            f"{quote(remote_path)} | cut -d ' ' -f 1)\" = {quote(expected_hash)}"
        )
    preflight_parts.extend(
        (
            _monitoring_compose_command("config", "--quiet"),
            "printf 'monitoring_deploy_preflight_ok\\n'",
        )
    )
    commands.append(
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(preflight_parts))]
    )

    old_names = " ".join(quote(name) for name in OLD_MONITORING_CONTAINERS)
    recovery = (
        "status=$?; trap - HUP INT TERM EXIT; "
        f"{_monitoring_compose_command('down')} >/dev/null 2>&1 || true; "
        f"docker start -- {old_names} >/dev/null 2>&1 || true; "
        "exit \"$status\""
    )
    cutover = (
        "set -eu; "
        f"trap {_shell_single_quote(recovery)} HUP INT TERM EXIT; "
        f"docker stop -- {old_names}; "
        "HOMEOPS_LAN_IP=127.0.0.1 "
        f"{_monitoring_compose_command('up', '-d', '--wait', '--wait-timeout', '180')}; "
        "docker exec -i homeops-monitoring-grafana-1 grafana cli --homepath "
        "/usr/share/grafana admin "
        "reset-admin-password --password-from-stdin "
        f"< {quote(REMOTE_MONITORING_SECRET)}; "
        f"{_grafana_protected_auth_check('http://127.0.0.1:3000/api/user')}; "
        f"{_grafana_default_auth_rejected_check('http://127.0.0.1:3000/api/user')}; "
        f"{_monitoring_compose_command('up', '-d', '--wait', '--wait-timeout', '180')}; "
        "trap - HUP INT TERM EXIT; "
        "printf 'monitoring_deployed\\n'"
    )
    commands.append(
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", cutover)]
    )

    verify_parts = [
        "set -eu",
        f"trap {_shell_single_quote(recovery)} HUP INT TERM EXIT",
    ]
    for name in OLD_MONITORING_CONTAINERS:
        verify_parts.append(
            "test \"$(docker inspect --type container --format "
            f"'{{{{.State.Running}}}}' {quote(name)})\" = false"
        )
    for name, image in NEW_MONITORING_CONTAINERS.items():
        verify_parts.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = true",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Health.Status}}}}' {quote(name)})\" = healthy",
            )
        )
    for name in (
        "homeops-monitoring-cadvisor-1",
        "homeops-monitoring-node-exporter-1",
        "homeops-monitoring-prometheus-1",
    ):
        verify_parts.append(f"test -z \"$(docker port {quote(name)})\"")
    verify_parts.append(
        "test \"$(docker port homeops-monitoring-grafana-1 3000/tcp)\" "
        "= 192.168.86.58:3000"
    )
    for volume in (*NEW_MONITORING_VOLUMES, *OLD_MONITORING_VOLUMES):
        verify_parts.append(f"docker volume inspect {quote(volume)} >/dev/null")
    verify_parts.extend(
        (
            _grafana_protected_auth_check(
                "http://192.168.86.58:3000/api/user"
            ),
            _grafana_default_auth_rejected_check(
                "http://192.168.86.58:3000/api/user"
            ),
            "if docker logs homeops-monitoring-grafana-1 2>&1 | grep -Eq "
            + _shell_single_quote(
                "Failed to install plugin|provisioning/(plugins|alerting).*"
                "no such file or directory|grafana_admin_password: Permission denied"
            )
            + "; then exit 1; fi",
        )
    )
    verify_parts.append("trap - HUP INT TERM EXIT")
    verify_parts.append("printf 'monitoring_deployment_verified\\n'")
    commands.append(
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(verify_parts))]
    )
    return commands


def _provision_monitoring_secret_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Generate a secret without logging its value and retain an ignored copy."""

    local_secret_dir = LOCAL_MONITORING_SECRET.parent
    if not local_secret_dir.is_dir():
        raise ActionError(
            "Local monitoring secret directory not found: "
            f"{local_secret_dir}"
        )

    remote_secret_dir = REMOTE_MONITORING_SECRET.rsplit("/", 1)[0]
    generation = "import secrets; print(secrets.token_urlsafe(32))"
    script = (
        "set -eu; "
        f"secret_dir={quote(remote_secret_dir)}; "
        f"secret={quote(REMOTE_MONITORING_SECRET)}; "
        "install -d -m 0700 \"$secret_dir\"; "
        "test \"$(stat -c %a \"$secret_dir\")\" = 700; "
        "test \"$(stat -c %u \"$secret_dir\")\" = \"$(id -u)\"; "
        "if [ -e \"$secret\" ] || [ -L \"$secret\" ]; then "
        "test -f \"$secret\"; test ! -L \"$secret\"; "
        "else "
        "tmp=$(mktemp \"$secret_dir/.grafana_admin_password.XXXXXX\"); "
        "trap 'rm -f \"$tmp\"' HUP INT TERM EXIT; "
        f"python3 -c {_shell_single_quote(generation)} > \"$tmp\"; "
        "chmod 0600 \"$tmp\"; mv \"$tmp\" \"$secret\"; "
        "trap - HUP INT TERM EXIT; "
        "fi; "
        "test -s \"$secret\"; test ! -L \"$secret\"; "
        "test \"$(stat -c %a \"$secret\")\" = 600; "
        "test \"$(stat -c %u \"$secret\")\" = \"$(id -u)\"; "
        "printf 'monitoring_secret_provisioned\\n'"
    )
    return [
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", script)],
        _build_scp_base_command(server)
        + [
            f"{server.ssh_target}:{REMOTE_MONITORING_SECRET}",
            str(LOCAL_MONITORING_SECRET),
        ],
    ]


def _repair_monitoring_grafana_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Apply bounded Grafana startup/auth fixes without replacing metric services."""

    for source, _ in MONITORING_DEPLOY_FILES:
        if not source.exists():
            raise ActionError(f"Monitoring repair file not found: {source}")

    candidate_compose = f"{REMOTE_MONITORING_DIR}/compose.candidate.yaml"
    backup_compose = f"{REMOTE_MONITORING_DIR}/compose.pre-repair.yaml"
    remote_directories = sorted(
        {
            REMOTE_MONITORING_DIR,
            *(
                f"{REMOTE_MONITORING_DIR}/{relative.rsplit('/', 1)[0]}"
                for _, relative in MONITORING_DEPLOY_FILES
                if "/" in relative
            ),
        }
    )
    commands: list[list[str]] = [
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("install", "-d", "-m", "0755", *remote_directories),
        ]
    ]
    for source, relative in MONITORING_DEPLOY_FILES:
        remote_path = (
            candidate_compose
            if relative == "compose.yaml"
            else f"{REMOTE_MONITORING_DIR}/{relative}"
        )
        commands.append(
            _build_scp_base_command(server)
            + [str(source), f"{server.ssh_target}:{remote_path}"]
        )

    validation_parts = ["set -eu"]
    for source, relative in MONITORING_DEPLOY_FILES:
        expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        remote_path = (
            candidate_compose
            if relative == "compose.yaml"
            else f"{REMOTE_MONITORING_DIR}/{relative}"
        )
        validation_parts.append(
            "test \"$(sha256sum "
            f"{quote(remote_path)} | cut -d ' ' -f 1)\" = {quote(expected_hash)}"
        )
    validation_parts.extend(
        (
            _remote_command(
                "docker",
                "compose",
                "--project-directory",
                REMOTE_MONITORING_DIR,
                "-f",
                candidate_compose,
                "config",
                "--quiet",
            ),
            "printf 'monitoring_grafana_candidate_valid\\n'",
        )
    )
    commands.append(
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("sh", "-lc", "; ".join(validation_parts)),
        ]
    )

    activation_parts = [
        "set -eu",
        f"test -s {quote(REMOTE_MONITORING_SECRET)}",
        f"test ! -L {quote(REMOTE_MONITORING_SECRET)}",
        "test \"$(stat -c %a "
        f"{quote(REMOTE_MONITORING_SECRET)})\" = 600",
    ]
    for name, image in OLD_MONITORING_CONTAINERS.items():
        activation_parts.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = false",
            )
        )
    for name, image in NEW_MONITORING_CONTAINERS.items():
        activation_parts.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = true",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Health.Status}}}}' {quote(name)})\" = healthy",
            )
        )
    activation_parts.extend(
        (
            f"cp -- {quote(REMOTE_MONITORING_COMPOSE)} {quote(backup_compose)}",
            f"mv -- {quote(candidate_compose)} {quote(REMOTE_MONITORING_COMPOSE)}",
            "printf 'monitoring_grafana_candidate_activated\\n'",
        )
    )
    commands.append(
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("sh", "-lc", "; ".join(activation_parts)),
        ]
    )

    recovery = (
        "status=$?; trap - HUP INT TERM EXIT; "
        f"cp -- {quote(backup_compose)} {quote(REMOTE_MONITORING_COMPOSE)}; "
        f"{_monitoring_compose_command('up', '-d', '--wait', '--wait-timeout', '180')} "
        ">/dev/null 2>&1 || true; "
        f"rm -f -- {quote(candidate_compose)} {quote(backup_compose)}; "
        "exit \"$status\""
    )
    repair = (
        "set -eu; "
        "cadvisor_id=$(docker inspect --format '{{.Id}}' "
        "homeops-monitoring-cadvisor-1); "
        "node_id=$(docker inspect --format '{{.Id}}' "
        "homeops-monitoring-node-exporter-1); "
        "prometheus_id=$(docker inspect --format '{{.Id}}' "
        "homeops-monitoring-prometheus-1); "
        f"trap {_shell_single_quote(recovery)} HUP INT TERM EXIT; "
        "HOMEOPS_LAN_IP=127.0.0.1 "
        f"{_monitoring_compose_command('up', '-d', '--wait', '--wait-timeout', '180')}; "
        "docker exec -i homeops-monitoring-grafana-1 grafana cli --homepath "
        "/usr/share/grafana admin "
        "reset-admin-password --password-from-stdin "
        f"< {quote(REMOTE_MONITORING_SECRET)}; "
        f"{_grafana_protected_auth_check('http://127.0.0.1:3000/api/user')}; "
        f"{_grafana_default_auth_rejected_check('http://127.0.0.1:3000/api/user')}; "
        f"{_monitoring_compose_command('up', '-d', '--wait', '--wait-timeout', '180')}; "
        "test \"$(docker inspect --format '{{.Id}}' "
        "homeops-monitoring-cadvisor-1)\" = \"$cadvisor_id\"; "
        "test \"$(docker inspect --format '{{.Id}}' "
        "homeops-monitoring-node-exporter-1)\" = \"$node_id\"; "
        "test \"$(docker inspect --format '{{.Id}}' "
        "homeops-monitoring-prometheus-1)\" = \"$prometheus_id\"; "
        "test \"$(docker exec homeops-monitoring-grafana-1 printenv "
        "GF_PLUGINS_PREINSTALL_DISABLED)\" = true; "
        "test \"$(docker exec homeops-monitoring-grafana-1 printenv "
        "GF_PLUGINS_PREINSTALL_AUTO_UPDATE)\" = false; "
        "test \"$(docker port homeops-monitoring-grafana-1 3000/tcp)\" "
        "= 192.168.86.58:3000; "
        f"{_grafana_protected_auth_check('http://192.168.86.58:3000/api/user')}; "
        f"{_grafana_default_auth_rejected_check('http://192.168.86.58:3000/api/user')}; "
        "if docker logs homeops-monitoring-grafana-1 2>&1 | grep -Eq "
        + _shell_single_quote(
            "Failed to install plugin|provisioning/(plugins|alerting).*"
            "no such file or directory|grafana_admin_password: Permission denied"
        )
        + "; then exit 1; fi; "
        "trap - HUP INT TERM EXIT; "
        f"rm -f -- {quote(backup_compose)}; "
        "printf 'monitoring_grafana_repair_verified\\n'"
    )
    commands.append(
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", repair)]
    )
    return commands


def _rollback_monitoring_stack_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Build a fixed rollback that restores the preserved proof-of-concept stack."""

    preflight_parts = ["set -eu", f"test -f {quote(REMOTE_MONITORING_COMPOSE)}"]
    for name, image in OLD_MONITORING_CONTAINERS.items():
        preflight_parts.append(
            "test \"$(docker inspect --type container --format "
            f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}"
        )
    for name, image in NEW_MONITORING_CONTAINERS.items():
        preflight_parts.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = true",
            )
        )
    preflight_parts.append("printf 'monitoring_rollback_preflight_ok\\n'")

    old_names = " ".join(quote(name) for name in OLD_MONITORING_CONTAINERS)
    restore_new = (
        "status=$?; trap - HUP INT TERM EXIT; "
        f"docker stop -- {old_names} >/dev/null 2>&1 || true; "
        f"{_monitoring_compose_command('start')} >/dev/null 2>&1 || true; "
        "exit \"$status\""
    )
    rollback = (
        "set -eu; "
        f"trap {_shell_single_quote(restore_new)} HUP INT TERM EXIT; "
        f"{_monitoring_compose_command('stop')}; "
        f"docker start -- {old_names}; "
        f"for name in {old_names}; do "
        "test \"$(docker inspect --type container --format "
        "'{{.State.Running}}' \"$name\")\" = true; done; "
        "trap - HUP INT TERM EXIT; "
        f"{_monitoring_compose_command('down', '--volumes')}; "
        "printf 'monitoring_rolled_back\\n'"
    )
    verify = (
        "set -eu; "
        f"for name in {old_names}; do "
        "test \"$(docker inspect --type container --format "
        "'{{.State.Running}}' \"$name\")\" = true; done; "
        f"for name in {' '.join(quote(name) for name in NEW_MONITORING_CONTAINERS)}; do "
        "if docker container inspect \"$name\" >/dev/null 2>&1; then exit 1; fi; done; "
        f"for volume in {' '.join(quote(volume) for volume in NEW_MONITORING_VOLUMES)}; do "
        "if docker volume inspect \"$volume\" >/dev/null 2>&1; then exit 1; fi; done; "
        "printf 'monitoring_rollback_verified\\n'"
    )
    return [
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(preflight_parts))],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", rollback)],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", verify)],
    ]


def _retire_legacy_monitoring_stack_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Remove accepted legacy monitoring state after proving desired state."""

    preflight_parts = ["set -eu"]
    for name, image in NEW_MONITORING_CONTAINERS.items():
        preflight_parts.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = true",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Health.Status}}}}' {quote(name)})\" = healthy",
            )
        )
    for name, image in OLD_MONITORING_CONTAINERS.items():
        preflight_parts.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = false",
            )
        )
    for volume in (*NEW_MONITORING_VOLUMES, *OLD_MONITORING_VOLUMES):
        preflight_parts.append(f"docker volume inspect {quote(volume)} >/dev/null")
    preflight_parts.extend(
        (
            _grafana_protected_auth_check(
                "http://192.168.86.58:3000/api/user"
            ),
            _grafana_default_auth_rejected_check(
                "http://192.168.86.58:3000/api/user"
            ),
            "printf 'legacy_monitoring_retirement_preflight_ok\\n'",
        )
    )

    old_names = " ".join(quote(name) for name in OLD_MONITORING_CONTAINERS)
    old_volumes = " ".join(quote(volume) for volume in OLD_MONITORING_VOLUMES)
    retire = (
        "set -eu; "
        f"docker rm -- {old_names}; "
        f"docker volume rm -- {old_volumes}; "
        "printf 'legacy_monitoring_retired\\n'"
    )

    verify_parts = ["set -eu"]
    for name in OLD_MONITORING_CONTAINERS:
        verify_parts.append(
            f"if docker container inspect {quote(name)} >/dev/null 2>&1; then exit 1; fi"
        )
    for volume in OLD_MONITORING_VOLUMES:
        verify_parts.append(
            f"if docker volume inspect {quote(volume)} >/dev/null 2>&1; then exit 1; fi"
        )
    for name in NEW_MONITORING_CONTAINERS:
        verify_parts.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = true",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Health.Status}}}}' {quote(name)})\" = healthy",
            )
        )
    for volume in NEW_MONITORING_VOLUMES:
        verify_parts.append(f"docker volume inspect {quote(volume)} >/dev/null")
    verify_parts.append("printf 'legacy_monitoring_retirement_verified\\n'")

    return [
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(preflight_parts))],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", retire)],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(verify_parts))],
    ]


def _retire_legacy_monitoring_files_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Remove only the verified obsolete monitoring Compose directory."""

    expected_members = "\n".join(sorted(LEGACY_MONITORING_FILES))
    remote_dir = quote(LEGACY_MONITORING_DIR)

    preflight_parts = ["set -eu"]
    for name, image in NEW_MONITORING_CONTAINERS.items():
        preflight_parts.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.Config.Image}}}}' {quote(name)})\" = {quote(image)}",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = true",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Health.Status}}}}' {quote(name)})\" = healthy",
            )
        )
    for name in OLD_MONITORING_CONTAINERS:
        preflight_parts.append(
            f"if docker container inspect {quote(name)} >/dev/null 2>&1; then exit 1; fi"
        )
    for volume in OLD_MONITORING_VOLUMES:
        preflight_parts.append(
            f"if docker volume inspect {quote(volume)} >/dev/null 2>&1; then exit 1; fi"
        )
    preflight_parts.extend(
        (
            f"test -d {remote_dir}",
            f"test ! -L {remote_dir}",
            f"test \"$(find {remote_dir} -xdev -mindepth 1 -maxdepth 1 "
            f"-printf '%f\\n' | LC_ALL=C sort)\" = {quote(expected_members)}",
        )
    )
    for name in LEGACY_MONITORING_FILES:
        path = quote(f"{LEGACY_MONITORING_DIR}/{name}")
        preflight_parts.extend((f"test -f {path}", f"test ! -L {path}"))
    preflight_parts.append("printf 'legacy_monitoring_files_preflight_ok\\n'")

    quoted_names = " ".join(quote(name) for name in LEGACY_MONITORING_FILES)
    retire_parts = [
        "set -eu",
        f"cd -- {remote_dir}",
        f"test \"$(pwd -P)\" = {remote_dir}",
        "test \"$(find . -xdev -mindepth 1 -maxdepth 1 -printf '%f\\n' | "
        f"LC_ALL=C sort)\" = {quote(expected_members)}",
    ]
    for name in LEGACY_MONITORING_FILES:
        retire_parts.extend((f"test -f {quote(name)}", f"test ! -L {quote(name)}"))
    retire_parts.extend(
        (
            f"rm -- {quoted_names}",
            "cd -- ..",
            f"rmdir -- {remote_dir}",
            "printf 'legacy_monitoring_files_retired\\n'",
        )
    )

    verify_parts = ["set -eu", f"test ! -e {remote_dir}"]
    for name in NEW_MONITORING_CONTAINERS:
        verify_parts.extend(
            (
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Running}}}}' {quote(name)})\" = true",
                "test \"$(docker inspect --type container --format "
                f"'{{{{.State.Health.Status}}}}' {quote(name)})\" = healthy",
            )
        )
    verify_parts.append("printf 'legacy_monitoring_files_retirement_verified\\n'")

    return [
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(preflight_parts))],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(retire_parts))],
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", "; ".join(verify_parts))],
    ]


def _inspect_storage_device_commands(
    server: ServerInventoryItem,
) -> list[list[str]]:
    """Report sanitized device and candidate mount metadata without mutation."""

    mount = quote(HOMEOPS_STORAGE_MOUNT)
    sentinel = quote(HOMEOPS_STORAGE_SENTINEL)
    mount_probe = (
        "set -eu; "
        f"if mountpoint -q {mount}; then "
        f"findmnt --json --bytes --output TARGET,SOURCE,FSTYPE,OPTIONS,FSROOT {mount}; "
        f"stat --printf='homeops_storage uid=%u gid=%g mode=%a bytes=%s\\n' {mount}; "
        f"if test -f {sentinel} && test ! -L {sentinel}; then "
        "printf 'homeops_storage_sentinel=present\\n'; "
        "else printf 'homeops_storage_sentinel=absent\\n'; fi; "
        "else printf 'homeops_storage_mount=absent\\n'; fi"
    )
    return [
        build_ssh_base_command(server)
        + [server.ssh_target, _remote_command("sh", "-lc", mount_probe)],
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command(
                "lsblk",
                "--json",
                "--bytes",
                "--output",
                "NAME,PATH,TYPE,SIZE,FSTYPE,FSVER,LABEL,UUID,MOUNTPOINTS,MODEL,TRAN",
            ),
        ],
    ]


def _monitoring_compose_command(*parts: str) -> str:
    return _remote_command(
        "docker",
        "compose",
        "--project-directory",
        REMOTE_MONITORING_DIR,
        "-f",
        REMOTE_MONITORING_COMPOSE,
        *parts,
    )


def _mission_control_compose_command(*parts: str) -> str:
    return _remote_command(
        "docker",
        "compose",
        "--project-directory",
        REMOTE_MISSION_CONTROL_DIR,
        "-f",
        REMOTE_MISSION_CONTROL_COMPOSE,
        *parts,
    )


def _grafana_protected_auth_check(endpoint: str) -> str:
    """Verify the protected admin credential without exposing it in argv/output."""

    script = (
        "import base64,urllib.request;"
        f"p=open({REMOTE_MONITORING_SECRET!r},encoding='utf-8').read().strip();"
        f"r=urllib.request.Request({endpoint!r},headers={{'Authorization':'Basic '+"
        "base64.b64encode(('admin:'+p).encode()).decode()});"
        "assert urllib.request.urlopen(r,timeout=10).status==200"
    )
    return _remote_command("python3", "-c", script)


def _grafana_default_auth_rejected_check(endpoint: str) -> str:
    """Require Grafana to reject the factory admin credential with HTTP 401."""

    script = (
        "import base64,urllib.error,urllib.request;"
        f"r=urllib.request.Request({endpoint!r},headers={{'Authorization':'Basic '+"
        "base64.b64encode(b'admin:admin').decode()});"
        "exec(\"try:\\n urllib.request.urlopen(r,timeout=10)\\nexcept "
        "urllib.error.HTTPError as e:\\n assert e.code==401\\nelse:\\n raise "
        "AssertionError('default credential accepted')\")"
    )
    return _remote_command("python3", "-c", script)


def _deploy_health_script_commands(server: ServerInventoryItem) -> list[list[str]]:
    if not LOCAL_HEALTH_SCRIPT_PATH.exists():
        raise ActionError(f"Local health script not found: {LOCAL_HEALTH_SCRIPT_PATH}")

    remote_target = f"{server.ssh_target}:{REMOTE_HEALTH_SCRIPT_PATH}"
    return [
        _build_scp_base_command(server) + [str(LOCAL_HEALTH_SCRIPT_PATH), remote_target],
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("chmod", "755", REMOTE_HEALTH_SCRIPT_PATH),
        ],
    ]


def _deploy_sudoers_profile_commands(server: ServerInventoryItem) -> list[list[str]]:
    if not SUDOERS_USER_RE.fullmatch(server.user):
        raise ActionError(
            "Server user is not safe for sudoers rendering: "
            f"{server.server_id} uses {server.user!r}."
        )

    profile = _render_sudoers_profile(server)
    script = (
        "tmp=$(mktemp) && "
        f"printf '%s' {_shell_single_quote(profile)} > \"$tmp\" && "
        "sudo -n /usr/sbin/visudo -cf \"$tmp\" && "
        f"sudo -n /usr/bin/install -o root -g root -m 0440 \"$tmp\" {REMOTE_SUDOERS_PATH} && "
        "rm -f \"$tmp\" && "
        f"sudo -n /usr/sbin/visudo -cf {REMOTE_SUDOERS_PATH}"
    )
    return [
        build_ssh_base_command(server)
        + [
            server.ssh_target,
            _remote_command("sh", "-lc", script),
        ]
    ]


def _render_sudoers_profile(server: ServerInventoryItem) -> str:
    template_name = SUDOERS_TEMPLATE_NAMES.get(server.access_profile)
    if not template_name:
        raise ActionError(
            "No approved sudoers template for access profile: "
            f"{server.access_profile}."
        )

    template_path = LOCAL_SUDOERS_TEMPLATE_DIR / template_name
    if not template_path.exists():
        raise ActionError(f"Local sudoers template not found: {template_path}")

    profile = template_path.read_text(encoding="utf-8").replace(
        "HOMEOPS_USER", server.user
    )
    return (
        "# Managed by HomeOps-Agent deploy_sudoers_profile.\n"
        f"# Source template: server-scripts/sudoers/{template_name}\n"
        f"{profile}"
    )


def _shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _build_scp_base_command(server: ServerInventoryItem) -> list[str]:
    command = [
        "scp",
        "-P",
        str(server.port),
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={server.connect_timeout_seconds}",
    ]
    if server.identity_file:
        command.extend(["-i", expanduser(expandvars(server.identity_file))])
    return command


def _remote_command(*parts: str) -> str:
    return " ".join(quote(part) for part in parts)


def _approved_service_name(
    server: ServerInventoryItem, arguments: dict[str, Any]
) -> str:
    service = str(arguments.get("service") or "")
    if not SERVICE_NAME_RE.fullmatch(service):
        raise ActionError(
            "Service name is required and may contain only letters, digits, "
            "periods, underscores, at signs, and dashes."
        )

    allowed = APPROVED_SERVICE_RESTARTS.get(server.role, {})
    normalized = allowed.get(service)
    if not normalized:
        approved_names = ", ".join(sorted(allowed)) or "none"
        raise ActionError(
            f"Service is not approved for restart on role {server.role}: {service}. "
            f"Approved services: {approved_names}."
        )
    return normalized


def _validated_admin_command(
    server: ServerInventoryItem, arguments: dict[str, Any]
) -> str:
    if not server.allows_admin_experiments:
        raise ActionError(
            "run_admin_command is allowed only for experimental or lab access "
            f"profiles. Server {server.server_id} is {server.access_profile}."
        )

    command = str(arguments.get("command") or "").strip()
    if not command:
        raise ActionError("Admin command is required. Pass --command.")
    if len(command) > ADMIN_COMMAND_MAX_LENGTH:
        raise ActionError(
            f"Admin command is too long. Limit: {ADMIN_COMMAND_MAX_LENGTH} characters."
        )
    if _has_control_character(command):
        raise ActionError(
            "Admin command must be a single line without control characters."
        )

    intent = str(arguments.get("intent") or "").strip()
    if not intent:
        raise ActionError("Admin command intent is required. Pass --intent.")
    if len(intent) > ADMIN_INTENT_MAX_LENGTH:
        raise ActionError(
            f"Admin command intent is too long. Limit: {ADMIN_INTENT_MAX_LENGTH} characters."
        )
    if _has_control_character(intent):
        raise ActionError("Admin command intent must be a single line.")

    arguments["command"] = command
    arguments["intent"] = intent
    return command


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 for character in value)


def write_action_record(record: dict[str, Any], actions_dir: Path | None = None) -> Path:
    """Write one action history record and return its path."""

    root = actions_dir or config.ACTIONS_DIR
    root.mkdir(parents=True, exist_ok=True)
    timestamp = str(record.get("timestamp") or config.utc_now_iso())
    action_id = str(record.get("action_id") or "unknown")
    server_id = str(record.get("server_id") or "unknown")
    base = f"{config.safe_timestamp(timestamp)}-{server_id}-{action_id}"
    path = root / f"{base}.json"
    suffix = 1
    while path.exists():
        path = root / f"{base}-{suffix}.json"
        suffix += 1
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _action_or_raise(action_id: str) -> dict[str, Any]:
    action = action_registry.get_action(action_id)
    if not action:
        raise ActionError(f"Unknown action_id: {action_id}")
    if not action.get("implemented"):
        raise ActionError(f"Action is registered but not implemented: {action_id}")
    return action


def _server_or_raise(
    server_id: str, servers: list[ServerInventoryItem]
) -> ServerInventoryItem:
    for server in servers:
        if server.server_id == server_id:
            return server
    raise ActionError(f"Enabled server not found in inventory: {server_id}")


def _validate_action_for_server(
    action: dict[str, Any], server: ServerInventoryItem
) -> None:
    allowed_roles = action.get("server_roles")
    if isinstance(allowed_roles, list) and server.role not in allowed_roles:
        raise ActionError(
            f"Action {action['action_id']} is not allowed for role {server.role}."
        )


def _validate_policy(
    action: dict[str, Any],
    command: list[str],
    server: ServerInventoryItem,
    policy_data: dict[str, Any],
) -> None:
    action_id = str(action.get("action_id"))
    risk = str(action.get("risk", "approval_required"))
    approval_required = policy_data.get("approval_required_actions") or []
    if risk == "approval_required" and action_id not in approval_required:
        raise ActionError(f"Policy does not allow approval-required action: {action_id}")

    if action_id == "run_admin_command" and server.access_profile == ACCESS_PROFILE_LAB:
        return

    command_text = " ".join(command).lower()
    for pattern in policy_data.get("forbidden_action_patterns") or []:
        normalized_pattern = str(pattern).lower()
        if normalized_pattern and normalized_pattern in command_text:
            raise ActionError(f"Command contains forbidden policy pattern: {pattern}")


def _base_record(
    action_id: str,
    server: ServerInventoryItem,
    arguments: dict[str, Any],
    risk: str,
    commands: list[list[str]],
    approval_source: str,
    dry_run: bool,
    expected_approval: str,
) -> dict[str, Any]:
    command = commands[0]
    return {
        "timestamp": config.utc_now_iso(),
        "server_id": server.server_id,
        "action_id": action_id,
        "arguments": arguments,
        "risk": risk,
        "access_profile": server.access_profile,
        "rebuildable": server.rebuildable,
        "approval_source": approval_source,
        "expected_approval": expected_approval,
        "dry_run": dry_run,
        "command": command,
        "commands": commands,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
    }


def _run_commands(
    commands: list[list[str]],
    server: ServerInventoryItem,
    *,
    command_timeout_seconds: int | None = None,
) -> dict[str, Any]:
    if len(commands) == 1:
        return _run_command(
            commands[0],
            server,
            command_timeout_seconds=command_timeout_seconds,
        )

    started = time.monotonic()
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []

    for index, command in enumerate(commands, start=1):
        result = _run_command(
            command,
            server,
            command_timeout_seconds=command_timeout_seconds,
        )
        if result["stdout"]:
            stdout_parts.append(f"command {index}: {result['stdout']}")
        if result["stderr"]:
            stderr_parts.append(f"command {index}: {result['stderr']}")
        if result["exit_code"] != 0:
            return {
                "exit_code": result["exit_code"],
                "stdout": "\n".join(stdout_parts),
                "stderr": "\n".join(stderr_parts),
                "duration_seconds": round(time.monotonic() - started, 3),
            }

    return {
        "exit_code": 0,
        "stdout": "\n".join(stdout_parts),
        "stderr": "\n".join(stderr_parts),
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def _run_command(
    command: list[str],
    server: ServerInventoryItem,
    *,
    command_timeout_seconds: int | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    remote_timeout = command_timeout_seconds or server.command_timeout_seconds
    timeout_seconds = server.connect_timeout_seconds + remote_timeout
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "SSH action command timed out.",
            "duration_seconds": round(time.monotonic() - started, 3),
        }

    return {
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def _summary(value: str, limit: int = 500) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    marker = " ...[truncated]... "
    available = limit - len(marker)
    head = available // 2
    tail = available - head
    return collapsed[:head] + marker + collapsed[-tail:]
