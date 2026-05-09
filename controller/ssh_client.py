"""Small SSH command wrapper for HomeOps collection."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from os.path import expanduser, expandvars

from .inventory import ServerInventoryItem, is_allowed_remote_health_command


@dataclass(frozen=True)
class RemoteCommandResult:
    server_id: str
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


def build_ssh_command(server: ServerInventoryItem) -> list[str]:
    """Build the local SSH command for one inventory item."""

    if not is_allowed_remote_health_command(server.remote_health_command):
        raise ValueError(
            f"Remote health command is not approved: {server.remote_health_command}"
        )

    command = build_ssh_base_command(server)
    command.extend([server.ssh_target, server.remote_health_command])
    return command


def build_ssh_base_command(server: ServerInventoryItem) -> list[str]:
    """Build common SSH options for one inventory item."""

    command = [
        "ssh",
        "-p",
        str(server.port),
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={server.connect_timeout_seconds}",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=2",
    ]
    if server.identity_file:
        command.extend(["-i", expanduser(expandvars(server.identity_file))])
    return command


def run_remote_command(server: ServerInventoryItem) -> RemoteCommandResult:
    """Run the configured read-only health command over SSH."""

    command = build_ssh_command(server)
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
        return RemoteCommandResult(
            server_id=server.server_id,
            command=command,
            exit_code=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "SSH command timed out.",
            duration_seconds=time.monotonic() - started,
            timed_out=True,
        )
    except FileNotFoundError:
        return RemoteCommandResult(
            server_id=server.server_id,
            command=command,
            exit_code=127,
            stdout="",
            stderr="ssh executable was not found on this machine.",
            duration_seconds=time.monotonic() - started,
        )

    return RemoteCommandResult(
        server_id=server.server_id,
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_seconds=time.monotonic() - started,
    )
