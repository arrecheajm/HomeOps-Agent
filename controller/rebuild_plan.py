"""Draft rebuild plan generation from before-state snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config
from .inventory import ServerInventoryItem


ALLOWED_STRATEGIES = ("repair", "reinstall", "repurpose")


class RebuildPlanError(RuntimeError):
    """Raised when a rebuild plan cannot be generated."""


@dataclass(frozen=True)
class RebuildPlan:
    payload: dict[str, Any]
    path: Path


def load_before_state(path: Path) -> dict[str, Any]:
    """Load a before-state snapshot from disk."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RebuildPlanError(f"Before-state snapshot not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RebuildPlanError(f"Invalid before-state JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise RebuildPlanError(f"Before-state snapshot must be a JSON object: {path}")
    if payload.get("snapshot_type") != "before_rebuild":
        raise RebuildPlanError(
            f"Before-state snapshot has unsupported type: {payload.get('snapshot_type')}"
        )
    return payload


def find_latest_before_state(server_id: str, root: Path | None = None) -> Path:
    """Return the latest before-state snapshot path for a server."""

    directory = root or config.BEFORE_STATE_DIR
    if not directory.exists():
        raise RebuildPlanError(
            f"No before-state snapshot directory found: {directory}"
        )

    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            payload = load_before_state(path)
        except RebuildPlanError:
            continue
        if str(payload.get("server_id") or "") == server_id:
            return path
    raise RebuildPlanError(f"No before-state snapshot found for server: {server_id}")


def build_rebuild_plan(
    server: ServerInventoryItem,
    before_state_payload: dict[str, Any],
    before_state_path: Path,
    goal: str,
    strategy: str,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a non-destructive rebuild plan from a before-state snapshot."""

    clean_goal = " ".join(str(goal or "").split())
    if not clean_goal:
        raise RebuildPlanError("Rebuild goal is required.")
    if strategy not in ALLOWED_STRATEGIES:
        allowed = ", ".join(ALLOWED_STRATEGIES)
        raise RebuildPlanError(f"Strategy must be one of: {allowed}.")
    if not server.rebuildable:
        raise RebuildPlanError(f"Server is not marked rebuildable: {server.server_id}.")

    snapshot_server_id = str(before_state_payload.get("server_id") or "")
    if snapshot_server_id != server.server_id:
        raise RebuildPlanError(
            "Before-state snapshot server does not match requested server: "
            f"{snapshot_server_id} != {server.server_id}."
        )

    readiness = before_state_payload.get("rebuild_readiness")
    if not isinstance(readiness, dict):
        readiness = {}
    blocked_reasons = [
        str(reason)
        for reason in readiness.get("blocked_reasons", [])
        if str(reason)
    ]

    actual_generated_at = generated_at or config.utc_now_iso()
    plan_id = _plan_id(actual_generated_at, server.server_id)
    return {
        "schema_version": "1.0",
        "plan_type": "rebuild_plan",
        "plan_id": plan_id,
        "generated_at": actual_generated_at,
        "status": "blocked" if blocked_reasons else "draft",
        "server_id": server.server_id,
        "role": server.role,
        "access_profile": server.access_profile,
        "rebuildable": server.rebuildable,
        "strategy": strategy,
        "goal": clean_goal,
        "before_state": {
            "path": _repo_path(before_state_path),
            "generated_at": str(before_state_payload.get("generated_at") or ""),
            "intent": str(before_state_payload.get("intent") or ""),
            "source_run": before_state_payload.get("source") or {},
        },
        "blocked_reasons": blocked_reasons,
        "preserve": _preservation_targets(server.role, before_state_payload),
        "phases": _plan_phases(server, strategy),
        "verification": _verification_steps(server.role),
        "future_destructive_approval": (
            f"Approve destructive rebuild plan {plan_id} on {server.server_id}"
        ),
        "execution_allowed": False,
        "notes": [
            "This plan is documentation only and does not execute server changes.",
            "Capture a fresh before-state snapshot if server state changes materially.",
        ],
    }


def write_rebuild_plan(
    server: ServerInventoryItem,
    before_state_payload: dict[str, Any],
    before_state_path: Path,
    goal: str,
    strategy: str,
    *,
    output_dir: Path | None = None,
    generated_at: str | None = None,
) -> RebuildPlan:
    """Write a rebuild plan JSON file."""

    payload = build_rebuild_plan(
        server,
        before_state_payload,
        before_state_path,
        goal,
        strategy,
        generated_at=generated_at,
    )
    root = output_dir or config.REBUILD_PLANS_DIR
    root.mkdir(parents=True, exist_ok=True)
    base = payload["plan_id"]
    path = root / f"{base}.json"
    suffix = 1
    while path.exists():
        path = root / f"{base}-{suffix}.json"
        suffix += 1
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return RebuildPlan(payload=payload, path=path)


def server_by_id(
    servers: list[ServerInventoryItem], server_id: str
) -> ServerInventoryItem:
    """Return one inventory server by ID."""

    for server in servers:
        if server.server_id == server_id:
            return server
    raise RebuildPlanError(f"Enabled server not found in inventory: {server_id}")


def _plan_id(generated_at: str, server_id: str) -> str:
    return f"{config.safe_timestamp(generated_at)}-{server_id}-rebuild-plan"


def _preservation_targets(
    role: str, before_state_payload: dict[str, Any]
) -> list[dict[str, Any]]:
    common = [
        {
            "name": "before-state snapshot",
            "reason": "Baseline evidence for rollback and comparison.",
            "source": _repo_path_from_payload(before_state_payload),
        },
        {
            "name": "SSH access",
            "reason": "Controller must regain access after rebuild.",
            "source": "inventory and authorized_keys",
        },
    ]
    if role == "ispy_server":
        common.extend(
            [
                {
                    "name": "AgentDVR configuration",
                    "reason": "Camera definitions and recording settings are role-critical.",
                    "source": "discover on host before destructive work",
                },
                {
                    "name": "recording paths",
                    "reason": "Preserve or intentionally discard recordings before wipe.",
                    "source": "disk and service evidence from before-state",
                },
                {
                    "name": "service units",
                    "reason": "Recreate only the active camera service and avoid stale units.",
                    "source": "before-state services list",
                },
            ]
        )
    elif role == "container_host":
        common.extend(
            [
                {
                    "name": "compose files and environment files",
                    "reason": "Needed to recreate containers after rebuild.",
                    "source": "discover on host before destructive work",
                },
                {
                    "name": "Docker volumes and bind mounts",
                    "reason": "Decide what data is disposable before wipe.",
                    "source": "container and filesystem inspection",
                },
                {
                    "name": "container inventory",
                    "reason": "Recreate only wanted workloads.",
                    "source": "before-state Docker summary and follow-up inspection",
                },
            ]
        )
    else:
        common.append(
            {
                "name": "role-specific configuration",
                "reason": "Unknown role needs manual preservation review.",
                "source": "manual inspection",
            }
        )
    return common


def _plan_phases(server: ServerInventoryItem, strategy: str) -> list[dict[str, Any]]:
    return [
        {
            "name": "confirm access and scope",
            "actions": [
                "Verify current access path does not depend on the target staying online.",
                f"Confirm {server.server_id} is still marked rebuildable in inventory.",
                "Review the before-state snapshot and recent action history.",
            ],
        },
        {
            "name": "preserve useful state",
            "actions": [
                "Copy or document preservation targets before destructive work.",
                "Record paths, package lists, service units, and workload definitions.",
                "Decide explicitly which data can be discarded.",
            ],
        },
        {
            "name": f"execute {strategy} manually",
            "actions": [
                "Use an out-of-band console or deliberate SSH session for destructive steps.",
                "Keep this controller plan as the checklist and audit reference.",
                "Do not run destructive disk commands through run_admin_command.",
            ],
        },
        {
            "name": "restore controller access",
            "actions": [
                "Recreate the configured user or update inventory deliberately.",
                "Install the controller SSH public key.",
                "Install the approved health script and matching sudoers profile.",
            ],
        },
        {
            "name": "verify rebuilt server",
            "actions": [
                "Run collection from the controller.",
                "Refresh dashboard and fleet catalog.",
                "Compare current findings against the before-state snapshot.",
            ],
        },
    ]


def _verification_steps(role: str) -> list[str]:
    steps = [
        "python -m controller.main collect --dry-run",
        "python -m controller.main collect",
        "python -m controller.main dashboard",
        "python -m controller.main catalog",
    ]
    if role == "ispy_server":
        steps.append("Verify AgentDVR service is active and camera feeds work.")
    elif role == "container_host":
        steps.append("Verify expected containers are running and unhealthy count is zero.")
    return steps


def _repo_path(path: Path) -> str:
    try:
        return str(path.relative_to(config.BASE_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _repo_path_from_payload(payload: dict[str, Any]) -> str:
    source = payload.get("source")
    if isinstance(source, dict):
        return str(source.get("fleet_path") or "")
    return ""
