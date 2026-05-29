"""Read-only AgentDVR evidence collection."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from shlex import quote
from typing import Any

from . import config
from .inventory import ServerInventoryItem
from .ssh_client import build_ssh_base_command


DEFAULT_OUTPUT_PATH = config.GENERATED_REPORTS_DIR / "ispy-agentdvr-evidence.json"
REMOTE_SCRIPT_PATH = config.BASE_DIR / "server-scripts" / "ispy" / "agentdvr_evidence.py"
REMOTE_PYTHON_COMMAND = "python3 -"


class AgentDvrEvidenceError(RuntimeError):
    """Raised when AgentDVR evidence collection fails."""


@dataclass(frozen=True)
class AgentDvrEvidenceResult:
    payload: dict[str, Any]
    output_path: Path
    command: list[str]
    duration_seconds: float


def build_agentdvr_evidence_command(server: ServerInventoryItem) -> list[str]:
    """Build the fixed read-only SSH command for AgentDVR evidence."""

    command = build_ssh_base_command(server)
    command.extend(
        [
            server.ssh_target,
            _remote_command("sudo", "-n", "/usr/bin/bash", "-lc", REMOTE_PYTHON_COMMAND),
        ]
    )
    return command


def collect_agentdvr_evidence(
    server: ServerInventoryItem,
    *,
    output_path: Path | None = None,
) -> AgentDvrEvidenceResult:
    """Run the remote evidence script and write sanitized JSON locally."""

    if server.role != "ispy_server":
        raise AgentDvrEvidenceError(
            f"AgentDVR evidence can only be collected from ispy_server, not {server.role}."
        )
    if not REMOTE_SCRIPT_PATH.exists():
        raise AgentDvrEvidenceError(f"Remote evidence script not found: {REMOTE_SCRIPT_PATH}")

    script = REMOTE_SCRIPT_PATH.read_text(encoding="utf-8")
    command = build_agentdvr_evidence_command(server)
    started = time.monotonic()
    timeout_seconds = server.connect_timeout_seconds + server.command_timeout_seconds

    try:
        completed = subprocess.run(
            command,
            input=script,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise AgentDvrEvidenceError(
            f"AgentDVR evidence command timed out: {exc.stderr or exc.stdout or ''}"
        ) from exc
    except FileNotFoundError as exc:
        raise AgentDvrEvidenceError("ssh executable was not found on this machine.") from exc

    if completed.returncode != 0:
        raise AgentDvrEvidenceError(
            "AgentDVR evidence command failed with exit code "
            f"{completed.returncode}: {_summary(completed.stderr)}"
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AgentDvrEvidenceError(f"AgentDVR evidence command returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AgentDvrEvidenceError("AgentDVR evidence command returned JSON that was not an object.")

    validate_agentdvr_evidence(payload)
    actual_output_path = output_path or DEFAULT_OUTPUT_PATH
    actual_output_path.parent.mkdir(parents=True, exist_ok=True)
    actual_output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return AgentDvrEvidenceResult(
        payload=payload,
        output_path=actual_output_path,
        command=command,
        duration_seconds=round(time.monotonic() - started, 3),
    )


def validate_agentdvr_evidence(payload: dict[str, Any]) -> None:
    """Validate the small schema consumed by the iSpy review report."""

    required = ("generated_at", "camera_count", "cameras", "endpoint_checks")
    missing = [key for key in required if key not in payload]
    if missing:
        raise AgentDvrEvidenceError(f"AgentDVR evidence is missing required keys: {missing}")
    if not isinstance(payload.get("cameras"), list):
        raise AgentDvrEvidenceError("AgentDVR evidence cameras must be a list.")
    if not isinstance(payload.get("endpoint_checks"), list):
        raise AgentDvrEvidenceError("AgentDVR evidence endpoint_checks must be a list.")
    for camera in payload.get("cameras") or []:
        if not isinstance(camera, dict):
            raise AgentDvrEvidenceError("AgentDVR evidence camera entries must be objects.")
        if "_source_uri" in camera or "source_uri" in camera:
            raise AgentDvrEvidenceError("AgentDVR evidence must not include stream URIs.")


def _remote_command(*parts: str) -> str:
    return " ".join(quote(part) for part in parts)


def _summary(value: str, limit: int = 500) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3] + "..."
