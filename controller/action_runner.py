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
    ACCESS_PROFILE_LAB,
    DEFAULT_REMOTE_HEALTH_COMMAND,
    ServerInventoryItem,
)
from .ssh_client import build_ssh_base_command


CONTAINER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]*$")
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
REMOTE_HEALTH_SCRIPT_PATH = DEFAULT_REMOTE_HEALTH_COMMAND
REBOOT_DELAY = "+1"
REBOOT_MESSAGE = "HomeOps-approved-reboot"
ADMIN_SHELL_PATH = "/usr/bin/bash"
ADMIN_COMMAND_MAX_LENGTH = 1000
ADMIN_INTENT_MAX_LENGTH = 240


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

    if action_id == "apply_security_updates":
        return [
            build_ssh_base_command(server)
            + [
                server.ssh_target,
                _remote_command("sudo", "-n", "unattended-upgrade"),
            ]
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
