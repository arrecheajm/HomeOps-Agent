"""Container host review and recommendation report generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from . import config, history, rules


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
    recommendations = _recommendations(
        server_id,
        server,
        server_findings,
        collection_errors,
        recent_actions,
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
) -> ContainerReview:
    """Write JSON and HTML container review reports."""

    payload = build_container_review(
        run,
        server_id,
        actions,
        generated_at=generated_at,
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
.topbar p, dt { color: var(--muted); }
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
