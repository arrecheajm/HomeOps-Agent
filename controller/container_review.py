"""Container host review and recommendation report generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from . import config, history, rules
from .container_evidence import (
    load_container_review_evidence,
    normalize_container_review_evidence,
)
from .docker_inventory import (
    inventory_collected,
    load_container_classifications,
    mount_labels,
    normalize_docker_inventory,
    port_labels,
)
from .workloads import load_workloads, normalize_workloads


DEFAULT_CONTAINER_SERVER_ID = "container-host"


@dataclass(frozen=True)
class ContainerReview:
    payload: dict[str, Any]
    json_path: Path
    html_path: Path


def build_container_review(
    run: history.RunSummary,
    server_id: str = DEFAULT_CONTAINER_SERVER_ID,
    actions: list[history.ActionSummary] | None = None,
    *,
    generated_at: str | None = None,
    evidence: dict[str, Any] | None = None,
    workloads: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic review for one container host."""

    server = _server_by_id(run, server_id)
    server_findings = _findings_for_server(run, server_id)
    collection_errors = _collection_errors_for_server(run, server_id)
    if not server and not collection_errors:
        collection_errors = [
            {
                "server_id": server_id,
                "message": "Server was not present in the source run.",
            }
        ]
    recent_actions = _recent_actions(actions or [], server_id)
    review_evidence = (
        normalize_container_review_evidence(evidence)
        if evidence is not None
        else load_container_review_evidence(
            config.CONTAINER_REVIEW_EVIDENCE_PATH,
            server_id,
        )
    )
    desired_workloads = (
        normalize_workloads(workloads)
        if workloads is not None
        else load_workloads(config.WORKLOADS_PATH, server_id)
    )
    recommendations = _recommendations(
        server_id,
        server,
        server_findings,
        collection_errors,
        recent_actions,
        review_evidence,
    )
    return {
        "schema_version": "1.0",
        "review_type": "container_review",
        "generated_at": generated_at or config.utc_now_iso(),
        "source": {
            "run_id": run.run_id,
            "generated_at": run.generated_at,
            "fleet_path": _repo_path(run.fleet_path),
        },
        "server_id": server_id,
        "server": _server_summary(server),
        "findings": server_findings,
        "collection_errors": collection_errors,
        "recent_actions": recent_actions,
        "evidence": review_evidence,
        "desired_state": desired_workloads,
        "recommendations": recommendations,
        "verification": [
            f"python -m controller.main collect --server {server_id}",
            f"python -m controller.main container-review --server {server_id}",
        ],
    }


def write_container_review(
    run: history.RunSummary,
    server_id: str = DEFAULT_CONTAINER_SERVER_ID,
    actions: list[history.ActionSummary] | None = None,
    *,
    output_dir: Path | None = None,
    generated_at: str | None = None,
    evidence: dict[str, Any] | None = None,
    workloads: dict[str, Any] | None = None,
) -> ContainerReview:
    """Write JSON and HTML container review reports."""

    payload = build_container_review(
        run,
        server_id,
        actions,
        generated_at=generated_at,
        evidence=evidence,
        workloads=workloads,
    )
    actual_output_dir = output_dir or config.GENERATED_REPORTS_DIR
    actual_output_dir.mkdir(parents=True, exist_ok=True)
    json_path = actual_output_dir / "container-review.json"
    html_path = actual_output_dir / "container-review.html"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    html_path.write_text(render_container_review(payload), encoding="utf-8")
    return ContainerReview(payload=payload, json_path=json_path, html_path=html_path)


def render_container_review(review: dict[str, Any]) -> str:
    """Render a container review report as HTML."""

    recommendations = _list(review.get("recommendations"))
    findings = _list(review.get("findings"))
    server = review.get("server") if isinstance(review.get("server"), dict) else {}
    body = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>HomeOps Container Review</title>",
        "<style>",
        _css(),
        "</style>",
        "</head>",
        "<body>",
        '<main class="shell">',
        '<header class="topbar">',
        "<div>",
        "<h1>HomeOps Container Review</h1>",
        f"<p>{escape(str(review.get('server_id', 'unknown')))} generated {escape(str(review.get('generated_at', 'unknown')))}</p>",
        "</div>",
        '<nav class="actions"><a href="index.html">Dashboard</a><a href="container-review.json">JSON</a></nav>',
        "</header>",
        _server_panel(server),
        _evidence_panel(_dict(review.get("evidence"))),
        _workloads_panel(_dict(review.get("desired_state"))),
        _container_inventory_panel(server),
        _findings_panel(findings),
        _recommendations_panel(recommendations),
        _verification_panel(_list(review.get("verification"))),
        "</main>",
        "</body>",
        "</html>",
    ]
    return "\n".join(body) + "\n"


def _server_by_id(run: history.RunSummary, server_id: str) -> dict[str, Any]:
    for server in run.servers:
        if str(server.get("server_id") or "") == server_id:
            return dict(server)
    return {}


def _findings_for_server(
    run: history.RunSummary, server_id: str
) -> list[dict[str, Any]]:
    return [
        dict(finding)
        for finding in run.findings
        if str(finding.get("server_id") or "") == server_id
    ]


def _collection_errors_for_server(
    run: history.RunSummary, server_id: str
) -> list[dict[str, Any]]:
    return [
        dict(error)
        for error in run.collection_errors
        if str(error.get("server_id") or "") == server_id
    ]


def _recent_actions(
    actions: list[history.ActionSummary], server_id: str, limit: int = 8
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for action in actions:
        if action.server_id != server_id:
            continue
        summaries.append(
            {
                "timestamp": action.timestamp,
                "action_id": action.action_id,
                "status": action.status,
                "dry_run": action.dry_run,
                "arguments": action.arguments,
                "approval_source": action.approval_source,
                "exit_code": action.exit_code,
                "record_path": _repo_path(action.record_path),
                "message": action.message,
                "stdout": _action_record_field(action.record_path, "stdout"),
                "stderr": _action_record_field(action.record_path, "stderr"),
            }
        )
        if len(summaries) >= limit:
            break
    return summaries


def _action_record_field(path: Path, field: str) -> str:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return ""
    if not isinstance(record, dict):
        return ""
    return str(record.get(field) or "")


def _server_summary(server: dict[str, Any]) -> dict[str, Any]:
    updates = _dict(server.get("updates"))
    docker = _dict(server.get("docker"))
    resources = _dict(server.get("resources"))
    classifications = load_container_classifications(
        config.CONTAINER_CLASSIFICATIONS_PATH,
        str(server.get("server_id") or DEFAULT_CONTAINER_SERVER_ID),
    )
    return {
        "hostname": str(server.get("hostname") or "unknown"),
        "role": str(server.get("role") or "unknown"),
        "collected_at": str(server.get("collected_at") or ""),
        "updates": {
            "pending_total": _as_int(updates.get("pending_total")),
            "pending_security": _as_int(updates.get("pending_security")),
            "reboot_required": bool(updates.get("reboot_required")),
        },
        "docker": {
            "installed": bool(docker.get("installed")),
            "containers_total": _as_int(docker.get("containers_total")),
            "containers_running": _as_int(docker.get("containers_running")),
            "inventory_collected": inventory_collected(docker),
            "containers": normalize_docker_inventory(docker, classifications),
            "unhealthy": [
                {
                    "name": str(item.get("name") or "unknown"),
                    "status": _clean_text(item.get("status"), "unknown"),
                }
                for item in docker.get("unhealthy", [])
                if isinstance(item, dict)
            ],
        },
        "resources": {
            "cpu_count": _as_int(resources.get("cpu_count")),
            "load_1m": _as_float(resources.get("load_1m")),
            "memory_used_percent": _as_float(resources.get("memory_used_percent")),
            "swap_used_percent": _as_float(resources.get("swap_used_percent")),
        },
        "services": [
            {
                "name": str(service.get("name") or "unknown"),
                "state": str(service.get("state") or "unknown"),
                "enabled": bool(service.get("enabled")),
            }
            for service in _list(server.get("services"))
            if isinstance(service, dict)
        ],
    }


def _recommendations(
    server_id: str,
    server: dict[str, Any],
    findings: list[dict[str, Any]],
    collection_errors: list[dict[str, Any]],
    recent_actions: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    if collection_errors:
        return [
            _recommendation(
                priority=1,
                severity="critical",
                title="Restore container host collection access",
                rationale=str(collection_errors[0].get("message") or "Collection failed."),
                dry_run_command=f"python -m controller.main collect --server {server_id} --dry-run",
            )
        ]

    recommendations: list[dict[str, Any]] = []
    docker = _dict(server.get("docker"))
    updates = _dict(server.get("updates"))
    classifications = load_container_classifications(
        config.CONTAINER_CLASSIFICATIONS_PATH,
        server_id,
    )
    inventory = normalize_docker_inventory(docker, classifications)

    if _sudo_password_blocked(recent_actions):
        recommendations.append(
            _recommendation(
                priority=5,
                severity="warning",
                title="Repair container host sudoers profile",
                rationale=(
                    "The latest approved admin inspection reached SSH but failed "
                    "because sudo requires a password. Install or repair the lab "
                    "sudoers profile before HomeOps can run package updates or "
                    "schedule a reboot. If sudo -n is already blocked, this needs "
                    "one manual root bootstrap with visudo."
                ),
                action_id="deploy_sudoers_profile",
                dry_run_command=(
                    "python -m controller.main actions run deploy_sudoers_profile "
                    f"--server {server_id} --dry-run"
                ),
            )
        )

    for container in docker.get("unhealthy", []) or []:
        if not isinstance(container, dict):
            continue
        container_name = str(container.get("name") or "").strip()
        if not container_name:
            continue
        status = _clean_text(container.get("status"), "unhealthy")
        if _docker_client_api_mismatch(recent_actions, container_name):
            recommendations.append(
                _recommendation(
                    priority=10,
                    severity="warning",
                    title=f"Migrate outdated {container_name} deployment",
                    rationale=(
                        f"Latest {container_name} logs show Docker client API "
                        "version 1.25 is too old for the host daemon minimum "
                        "1.40. Recreating the same containrrr/watchtower image "
                        "did not resolve the loop; migrate to the maintained "
                        "nickfedor/watchtower image with the captured HomeOps "
                        "options."
                    ),
                    action_id="migrate_watchtower_container",
                    dry_run_command=(
                        "python -m controller.main actions run migrate_watchtower_container "
                        f"--server {server_id} --dry-run"
                    ),
                )
            )
        else:
            recommendations.append(
                _recommendation(
                    priority=10,
                    severity="warning",
                    title=f"Inspect {container_name} restart loop",
                    rationale=(
                        f"Container {container_name} is reporting {status}. Read "
                        "container status and logs before restart."
                    ),
                    action_id="inspect_docker_container",
                    dry_run_command=(
                        "python -m controller.main actions run inspect_docker_container "
                        f"--server {server_id} --container {container_name} --dry-run"
                    ),
                )
            )
            recommendations.append(
                _recommendation(
                    priority=20,
                    severity="warning",
                    title=f"Restart {container_name} if logs show a transient failure",
                    rationale="Restart only after reviewing logs and confirming the failure is not caused by bad configuration.",
                    action_id="restart_docker_container",
                    dry_run_command=(
                        "python -m controller.main actions run restart_docker_container "
                        f"--server {server_id} --container {container_name} --dry-run"
                    ),
                )
            )

    if _docker_service_failed(server):
        recommendations.append(
            _recommendation(
                priority=30,
                severity="warning",
                title="Restart Docker service if service health degrades",
                rationale="Docker service is not active in the latest server health data.",
                action_id="restart_service",
                dry_run_command=(
                    "python -m controller.main actions run restart_service "
                    f"--server {server_id} --service docker.service --dry-run"
                ),
            )
        )

    pending_total = _as_int(updates.get("pending_total"))
    pending_security = _as_int(updates.get("pending_security"))
    if pending_total:
        recommendations.append(
            _recommendation(
                priority=40,
                severity="info",
                title="Apply pending package updates",
                rationale=(
                    f"{pending_total} package updates are pending on the "
                    "container host. Use the scoped package update action for "
                    "this lab host rather than a broad admin shell command."
                ),
                action_id="apply_package_updates",
                dry_run_command=(
                    "python -m controller.main actions run apply_package_updates "
                    f"--server {server_id} --dry-run"
                ),
            )
        )
    if pending_security:
        recommendations.append(
            _recommendation(
                priority=45,
                severity="warning",
                title="Apply security updates",
                rationale=f"{pending_security} security updates are pending.",
                action_id="apply_security_updates",
                dry_run_command=(
                    "python -m controller.main actions run apply_security_updates "
                    f"--server {server_id} --dry-run"
                ),
            )
        )

    if updates.get("reboot_required"):
        recommendations.append(
            _recommendation(
                priority=50,
                severity="warning",
                title="Plan a container host reboot",
                rationale="The container host reports that a reboot is required. Reboot after inspecting container impact.",
                action_id="reboot_server",
                dry_run_command=(
                    "python -m controller.main actions run reboot_server "
                    f"--server {server_id} --dry-run"
                ),
            )
        )

    evidence_storage = _dict(evidence.get("storage"))
    storage_targets = [
        item
        for item in _list(evidence_storage.get("targets"))
        if isinstance(item, dict)
    ]
    if storage_targets and all(
        str(item.get("backing_target") or "") == "/" for item in storage_targets
    ):
        paths = ", ".join(str(item.get("path") or "unknown") for item in storage_targets)
        recommendations.append(
            _recommendation(
                priority=55,
                severity="info",
                title="Reserve real external storage before household data deployment",
                rationale=(
                    f"{paths} are directories on the root filesystem, not external "
                    "storage, and no storage sentinel is present. Keep the planned "
                    "1 TB USB filesystem separate and require a mount/sentinel "
                    "preflight before Paperless or document data starts."
                ),
            )
        )

    database_evidence = [
        item for item in _list(evidence.get("databases")) if isinstance(item, dict)
    ]
    databases_requiring_preservation = [
        item
        for item in database_evidence
        if item.get("preservation_required") is not False
    ]
    if databases_requiring_preservation:
        database_summary = ", ".join(
            f"{item.get('container', 'unknown')} ({_format_bytes(_as_int(item.get('volume_bytes')))})"
            for item in databases_requiring_preservation
        )
        recommendations.append(
            _recommendation(
                priority=58,
                severity="info",
                title="Capture logical backups before deciding legacy database fate",
                rationale=(
                    f"Point-in-time evidence found {database_summary}. No application "
                    "container peers were identified. Export and restore-test each "
                    "database before removing either container or named volume."
                ),
            )
        )

    disposition_groups: dict[str, list[str]] = {}
    for container in inventory:
        disposition = str(container.get("classification") or "unclassified")
        disposition_groups.setdefault(disposition, []).append(
            str(container.get("name") or "unknown")
        )
    if disposition_groups.get("review"):
        names = ", ".join(disposition_groups["review"])
        recommendations.append(
            _recommendation(
                priority=60,
                severity="info",
                title="Resolve containers that need ownership and data review",
                rationale=(
                    f"Review {names} before cleanup. These containers expose broad "
                    "storage or persistent database data that must be identified and "
                    "backed up before a keep/remove decision."
                ),
            )
        )
    if disposition_groups.get("retire_now"):
        names = ", ".join(disposition_groups["retire_now"])
        recommendations.append(
            _recommendation(
                priority=65,
                severity="info",
                title="Retire confirmed disposable containers",
                rationale=(
                    f"The operator confirmed {names} and their application data "
                    "are disposable. The bounded action checks the expected images "
                    "and named volumes before removing only this fixed bundle."
                ),
                action_id="retire_disposable_containers",
                dry_run_command=(
                    "python -m controller.main actions run "
                    "retire_disposable_containers --server container-host --dry-run"
                ),
            )
        )
    if disposition_groups.get("redeploy"):
        names = ", ".join(disposition_groups["redeploy"])
        recommendations.append(
            _recommendation(
                priority=70,
                severity="info",
                title="Move useful monitoring services into desired state",
                rationale=(
                    f"Redeploy {names} with pinned images, restart policies, and "
                    "reviewed LAN bindings while preserving useful data."
                ),
            )
        )
    if disposition_groups.get("retire_later"):
        names = ", ".join(disposition_groups["retire_later"])
        recommendations.append(
            _recommendation(
                priority=80,
                severity="info",
                title="Retire management overlap after HomeOps replacements exist",
                rationale=(
                    f"Keep {names} temporarily, then retire them after HomeOps "
                    "provides the replacement management and controlled-upgrade "
                    "workflows."
                ),
            )
        )

    if not recommendations and findings:
        recommendations.append(
            _recommendation(
                priority=90,
                severity="info",
                title="Review remaining findings manually",
                rationale="The latest findings do not map to a specialized container workflow yet.",
            )
        )
    if not recommendations:
        recommendations.append(
            _recommendation(
                priority=100,
                severity="info",
                title="No container remediation needed",
                rationale="No Docker, reboot, update, or collection issues were found for the container host.",
            )
        )

    return sorted(
        recommendations,
        key=lambda item: (
            item["priority"],
            -rules.SEVERITY_RANK.get(str(item.get("severity")), 0),
            str(item.get("title")),
        ),
    )


def _recommendation(
    *,
    priority: int,
    severity: str,
    title: str,
    rationale: str,
    action_id: str | None = None,
    dry_run_command: str | None = None,
) -> dict[str, Any]:
    return {
        "priority": priority,
        "severity": severity,
        "title": title,
        "rationale": rationale,
        "action_id": action_id,
        "dry_run_command": dry_run_command,
    }


def _docker_service_failed(server: dict[str, Any]) -> bool:
    for service in _list(server.get("services")):
        if not isinstance(service, dict):
            continue
        if str(service.get("name") or "") == "docker":
            return str(service.get("state") or "unknown") != "active"
    return False


def _sudo_password_blocked(actions: list[dict[str, Any]]) -> bool:
    sudo_actions = {
        "run_admin_command",
        "apply_package_updates",
        "apply_security_updates",
        "reboot_server",
        "restart_service",
        "deploy_health_script",
        "deploy_sudoers_profile",
    }
    for action in actions:
        action_id = str(action.get("action_id") or "")
        if action_id not in sudo_actions:
            continue
        status = str(action.get("status") or "")
        if status == "completed":
            return False
        if status != "failed":
            continue
        stderr = str(action.get("stderr") or "").lower()
        if "sudo" in stderr and "password is required" in stderr:
            return True
    return False


def _docker_client_api_mismatch(
    actions: list[dict[str, Any]], container_name: str
) -> bool:
    for action in actions:
        if str(action.get("action_id") or "") != "inspect_docker_container":
            continue
        if str(action.get("status") or "") != "completed":
            continue
        arguments = _dict(action.get("arguments"))
        if str(arguments.get("container") or "") != container_name:
            continue
        combined_output = " ".join(
            [
                str(action.get("stdout") or ""),
                str(action.get("stderr") or ""),
            ]
        ).lower()
        if (
            "client version" in combined_output
            and "too old" in combined_output
            and "minimum supported api version" in combined_output
        ):
            return True
    return False


def _server_panel(server: dict[str, Any]) -> str:
    updates = _dict(server.get("updates"))
    docker = _dict(server.get("docker"))
    resources = _dict(server.get("resources"))
    return (
        '<section class="panel">'
        "<h2>Server State</h2>"
        '<dl class="facts">'
        f"<div><dt>Hostname</dt><dd>{escape(str(server.get('hostname', 'unknown')))}</dd></div>"
        f"<div><dt>Collected</dt><dd>{escape(str(server.get('collected_at', '')))}</dd></div>"
        f"<div><dt>Containers</dt><dd>{docker.get('containers_running', 0)}/{docker.get('containers_total', 0)}</dd></div>"
        f"<div><dt>Updates</dt><dd>{updates.get('pending_total', 0)}</dd></div>"
        f"<div><dt>Reboot</dt><dd>{'yes' if updates.get('reboot_required') else 'no'}</dd></div>"
        f"<div><dt>Memory</dt><dd>{resources.get('memory_used_percent', 0)}%</dd></div>"
        "</dl>"
        "</section>"
    )


def _evidence_panel(evidence: dict[str, Any]) -> str:
    if not evidence:
        return ""
    storage = _dict(evidence.get("storage"))
    root = _dict(storage.get("root_filesystem"))
    disk = _dict(storage.get("host_disk"))
    target_rows = []
    for target in _list(storage.get("targets")):
        if not isinstance(target, dict):
            continue
        target_rows.append(
            "<tr>"
            f"<td><code>{escape(str(target.get('path') or 'unknown'))}</code></td>"
            f"<td><code>{escape(str(target.get('backing_target') or 'unknown'))}</code><br>{escape(str(target.get('source') or 'unknown'))}</td>"
            f"<td>{escape(str(target.get('filesystem') or 'unknown'))}</td>"
            f"<td>{escape(_format_bytes(_as_int(target.get('aggregate_bytes'))))}</td>"
            f"<td>{_as_int(target.get('top_level_directories'))}</td>"
            f"<td>{'present' if target.get('sentinel_present') else 'absent'}</td>"
            "</tr>"
        )

    database_rows = []
    for database in _list(evidence.get("databases")):
        if not isinstance(database, dict):
            continue
        peers = ", ".join(str(item) for item in _list(database.get("application_peers"))) or "none"
        discovered = ", ".join(
            f"{item.get('name', 'unknown')} ({_format_bytes(_as_int(item.get('size_bytes')))})"
            for item in _list(database.get("databases"))
            if isinstance(item, dict)
        ) or "not enumerated"
        database_rows.append(
            "<tr>"
            f"<td><code>{escape(str(database.get('container') or 'unknown'))}</code></td>"
            f"<td>{escape(str(database.get('engine') or 'unknown'))}</td>"
            f"<td><code>{escape(str(database.get('volume') or 'unknown'))}</code><br>{escape(_format_bytes(_as_int(database.get('volume_bytes'))))}</td>"
            f"<td>{escape(peers)}</td>"
            f"<td>{'yes' if database.get('preservation_required') else 'no'}</td>"
            f"<td>{escape(str(database.get('query_status') or 'unknown'))}<br>{escape(discovered)}</td>"
            "</tr>"
        )

    return (
        '<section class="panel"><h2>Storage and Database Evidence</h2>'
        f'<p class="muted">Observed {escape(str(evidence.get("observed_at") or "unknown"))} using {escape(str(evidence.get("method") or "read-only inspection"))}. File names, file contents, credentials, and environment values were not collected.</p>'
        '<dl class="facts">'
        f"<div><dt>Host disk</dt><dd>{escape(str(disk.get('model') or 'unknown'))}<br>{escape(_format_bytes(_as_int(disk.get('size_bytes'))))}</dd></div>"
        f"<div><dt>Root filesystem</dt><dd>{escape(str(root.get('filesystem') or 'unknown'))}<br>{escape(_format_bytes(_as_int(root.get('size_bytes'))))}</dd></div>"
        f"<div><dt>Root available</dt><dd>{escape(_format_bytes(_as_int(root.get('available_bytes'))))}</dd></div>"
        f"<div><dt>Root used</dt><dd>{_as_int(root.get('used_percent'))}%</dd></div>"
        f"<div><dt>External device</dt><dd>{'detected' if storage.get('external_device_detected') else 'not detected'}</dd></div>"
        f"<div><dt>Sensitive content</dt><dd>{'collected' if evidence.get('sensitive_content_collected') else 'not collected'}</dd></div>"
        "</dl>"
        '<h3>Legacy storage paths</h3><div class="table-wrap"><table>'
        '<thead><tr><th>Path</th><th>Backing mount</th><th>Filesystem</th><th>Aggregate data</th><th>Top-level dirs</th><th>Sentinel</th></tr></thead><tbody>'
        + "".join(target_rows)
        + "</tbody></table></div>"
        '<h3>Legacy databases</h3><div class="table-wrap"><table>'
        '<thead><tr><th>Container</th><th>Engine</th><th>Volume</th><th>Application peers</th><th>Preserve</th><th>Read-only query</th></tr></thead><tbody>'
        + "".join(database_rows)
        + "</tbody></table></div></section>"
    )


def _container_inventory_panel(server: dict[str, Any]) -> str:
    docker = _dict(server.get("docker"))
    if not docker.get("installed"):
        return ""
    if not docker.get("inventory_collected"):
        return (
            '<section class="panel"><h2>Container Inventory</h2>'
            '<p class="muted">Detailed inventory was not collected in the source run. '
            "Deploy the updated read-only health script before classifying containers.</p>"
            "</section>"
        )
    containers = _list(docker.get("containers"))
    if not containers:
        return (
            '<section class="panel"><h2>Container Inventory</h2>'
            "<p>No containers found.</p></section>"
        )

    rows = []
    for container in containers:
        if not isinstance(container, dict):
            continue
        state = str(container.get("state") or "unknown")
        health = str(container.get("health") or "none")
        if health != "none":
            state = f"{state} / {health}"
        compose = str(container.get("compose_project") or "standalone")
        compose_service = str(container.get("compose_service") or "")
        if compose_service:
            compose = f"{compose}/{compose_service}"
        ports = port_labels(container)
        mounts = mount_labels(container)
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(container.get('name') or 'unknown'))}</code></td>"
            f"<td><code>{escape(str(container.get('image') or 'unknown'))}</code></td>"
            f"<td>{escape(state)}</td>"
            f"<td>{escape(compose)}</td>"
            f"<td>{escape(str(container.get('restart_policy') or 'unknown'))}</td>"
            f"<td>{escape(str(container.get('exposure') or 'unknown'))}<br>{'<br>'.join(escape(item) for item in ports) if ports else 'none'}</td>"
            f"<td>{'<br>'.join(escape(item) for item in mounts) if mounts else 'none'}</td>"
            f"<td><strong>{escape(str(container.get('classification') or 'unclassified'))}</strong><br>{escape(str(container.get('classification_rationale') or ''))}</td>"
            "</tr>"
        )
    return (
        '<section class="panel"><h2>Container Inventory</h2>'
        '<p class="muted">Sanitized inventory excludes logs, environment values, and secret data.</p>'
        '<div class="table-wrap"><table>'
        "<thead><tr><th>Name</th><th>Image</th><th>State</th><th>Compose</th><th>Restart</th><th>Exposure</th><th>Mounts</th><th>Review</th></tr></thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table></div></section>"
    )


def _workloads_panel(desired_state: dict[str, Any]) -> str:
    workloads = _list(desired_state.get("workloads"))
    if not workloads:
        return ""
    rows = []
    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        services = ", ".join(str(item) for item in _list(workload.get("services"))) or "none"
        prerequisites = "<br>".join(
            escape(str(item)) for item in _list(workload.get("prerequisites"))
        ) or "none"
        rows.append(
            "<tr>"
            f"<td>{_as_int(workload.get('phase'))}</td>"
            f"<td><code>{escape(str(workload.get('workload_id') or 'unknown'))}</code><br>{escape(str(workload.get('purpose') or ''))}</td>"
            f"<td>{escape(str(workload.get('state') or 'planned'))}</td>"
            f"<td>{escape(services)}</td>"
            f"<td>{escape(str(workload.get('storage_class') or 'internal'))}</td>"
            f"<td>{prerequisites}</td>"
            f"<td>{'enabled' if workload.get('deployment_enabled') else 'gated'}</td>"
            "</tr>"
        )
    return (
        '<section class="panel"><h2>Desired Workloads</h2>'
        f'<p class="muted">Network scope: {escape(str(desired_state.get("network_scope") or "lan_only"))}. Deployment remains gated until each workload has version-pinned Compose definitions and its listed prerequisites pass.</p>'
        '<div class="table-wrap"><table><thead><tr><th>Phase</th><th>Workload</th><th>State</th><th>Services</th><th>Storage</th><th>Prerequisites</th><th>Deployment</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div></section>"
    )


def _findings_panel(findings: list[Any]) -> str:
    if not findings:
        return '<section class="panel"><h2>Findings</h2><p>No findings for this server.</p></section>'
    rows = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        severity = str(finding.get("severity") or "info")
        rows.append(
            "<tr>"
            f'<td><span class="badge badge-{escape(severity)}">{escape(severity)}</span></td>'
            f"<td><code>{escape(str(finding.get('code', 'unknown')))}</code></td>"
            f"<td>{escape(str(finding.get('message', '')))}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>Findings</h2>"
        '<table><thead><tr><th>Severity</th><th>Code</th><th>Message</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></section>"
    )


def _recommendations_panel(recommendations: list[Any]) -> str:
    rows = []
    for item in recommendations:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "info")
        command = str(item.get("dry_run_command") or "")
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('priority', '')))}</td>"
            f'<td><span class="badge badge-{escape(severity)}">{escape(severity)}</span></td>'
            f"<td><strong>{escape(str(item.get('title', '')))}</strong><br>{escape(str(item.get('rationale', '')))}</td>"
            f"<td><code>{escape(str(item.get('action_id') or 'none'))}</code></td>"
            f"<td>{'<code>' + escape(command) + '</code>' if command else 'none'}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>Recommended Next Steps</h2>"
        '<table><thead><tr><th>Priority</th><th>Severity</th><th>Recommendation</th><th>Action</th><th>Dry Run</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></section>"
    )


def _verification_panel(verification: list[Any]) -> str:
    return (
        '<section class="panel">'
        "<h2>Verification</h2>"
        "<ul>"
        + "".join(f"<li><code>{escape(str(item))}</code></li>" for item in verification)
        + "</ul>"
        "</section>"
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _format_bytes(value: int) -> str:
    amount = float(max(0, value))
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{int(value)} B"


def _clean_text(value: Any, default: str) -> str:
    cleaned = " ".join(str(value or "").split())
    return cleaned or default


def _repo_path(path: Path) -> str:
    try:
        return str(path.relative_to(config.BASE_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _css() -> str:
    return """
:root {
  color-scheme: light;
  --bg: #f5f7f9;
  --panel: #ffffff;
  --text: #1f2933;
  --muted: #667085;
  --border: #d7dee8;
  --info: #2d6cdf;
  --warning: #9a5b00;
  --critical: #b42318;
  --accent: #31686f;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: "Segoe UI", Arial, sans-serif;
  line-height: 1.45;
}
.shell {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 28px 0 48px;
}
.topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 22px;
}
h1, h2, p { margin-top: 0; }
h1 { font-size: 32px; margin-bottom: 4px; }
h2 { font-size: 20px; }
p, td, th, li, dd, dt { font-size: 14px; }
.topbar p, dt, .muted { color: var(--muted); }
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
a {
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
}
.actions a {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 10px;
  background: var(--panel);
}
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 18px;
  padding: 18px;
}
.facts {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}
.facts div {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
}
dd { margin: 0; font-weight: 700; overflow-wrap: anywhere; }
table {
  width: 100%;
  border-collapse: collapse;
}
.table-wrap { overflow-x: auto; }
th, td {
  border-bottom: 1px solid var(--border);
  padding: 8px;
  text-align: left;
  vertical-align: top;
}
code {
  font-family: Consolas, "Courier New", monospace;
  font-size: 0.95em;
  overflow-wrap: anywhere;
}
.badge {
  border-radius: 999px;
  display: inline-block;
  font-weight: 700;
  padding: 2px 8px;
}
.badge-critical { background: #fdecea; color: var(--critical); }
.badge-warning { background: #fff4db; color: var(--warning); }
.badge-info { background: #eaf1ff; color: var(--info); }
@media (max-width: 920px) {
  .topbar { display: block; }
  .actions { margin-top: 10px; }
  .facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .facts { grid-template-columns: 1fr; }
}
"""
