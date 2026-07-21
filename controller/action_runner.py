"""Approval-gated action execution for predefined HomeOps actions."""

from __future__ import annotations

import json
import re
import subprocess
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
LOCAL_MONITORING_DIR = config.BASE_DIR / "stacks" / "monitoring"
LOCAL_PROMETHEUS_CONFIG_PATH = LOCAL_MONITORING_DIR / "prometheus" / "prometheus.yml"
LOCAL_PROMETHEUS_RULES_PATH = (
    LOCAL_MONITORING_DIR / "prometheus" / "rules" / "host.rules.yml"
)
REMOTE_PROMETHEUS_PREFLIGHT_CONFIG = "/tmp/homeops-prometheus-preflight.yml"
REMOTE_PROMETHEUS_PREFLIGHT_RULES = "/tmp/homeops-host-rules-preflight.yml"


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

    result = _run_commands(commands, server)
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
                    "command -v wget >/dev/null",
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


def _run_commands(commands: list[list[str]], server: ServerInventoryItem) -> dict[str, Any]:
    if len(commands) == 1:
        return _run_command(commands[0], server)

    started = time.monotonic()
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []

    for index, command in enumerate(commands, start=1):
        result = _run_command(command, server)
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


def _run_command(command: list[str], server: ServerInventoryItem) -> dict[str, Any]:
    started = time.monotonic()
    timeout_seconds = server.connect_timeout_seconds + server.command_timeout_seconds
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
    return collapsed[: limit - 3] + "..."
