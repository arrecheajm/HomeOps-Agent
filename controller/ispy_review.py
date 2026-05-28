"""iSpy server review and reliability report generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from . import config, history, rules


DEFAULT_ISPY_SERVER_ID = "ispy-server"


@dataclass(frozen=True)
class IspyReview:
    payload: dict[str, Any]
    json_path: Path
    html_path: Path


def build_ispy_review(
    run: history.RunSummary,
    server_id: str = DEFAULT_ISPY_SERVER_ID,
    actions: list[history.ActionSummary] | None = None,
    *,
    before_state: dict[str, Any] | None = None,
    before_state_path: Path | None = None,
    agentdvr_evidence: dict[str, Any] | None = None,
    agentdvr_evidence_path: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic review for the iSpy/AgentDVR server."""

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
    service_diagnosis = _service_diagnosis(server)
    reliability_checks = _reliability_checks(
        server,
        service_diagnosis,
        before_state,
        agentdvr_evidence,
    )
    recommendations = _recommendations(
        server_id,
        server,
        server_findings,
        collection_errors,
        recent_actions,
        before_state,
        agentdvr_evidence,
        service_diagnosis,
        reliability_checks,
    )
    return {
        "schema_version": "1.0",
        "review_type": "ispy_review",
        "generated_at": generated_at or config.utc_now_iso(),
        "source": {
            "run_id": run.run_id,
            "generated_at": run.generated_at,
            "fleet_path": _repo_path(run.fleet_path),
        },
        "server_id": server_id,
        "server": _server_summary(server),
        "before_state": _before_state_summary(before_state, before_state_path),
        "agentdvr_evidence": _agentdvr_evidence_summary(
            agentdvr_evidence,
            agentdvr_evidence_path,
        ),
        "findings": server_findings,
        "collection_errors": collection_errors,
        "recent_actions": recent_actions,
        "service_diagnosis": service_diagnosis,
        "reliability_checks": reliability_checks,
        "recommendations": recommendations,
        "verification": [
            f"python -m controller.main collect --server {server_id}",
            f"python -m controller.main ispy-review --server {server_id}",
            (
                "python -m controller.main check --input "
                f"{_repo_path(run.fleet_path)}"
            ),
        ],
    }


def write_ispy_review(
    run: history.RunSummary,
    server_id: str = DEFAULT_ISPY_SERVER_ID,
    actions: list[history.ActionSummary] | None = None,
    *,
    before_state: dict[str, Any] | None = None,
    before_state_path: Path | None = None,
    agentdvr_evidence: dict[str, Any] | None = None,
    agentdvr_evidence_path: Path | None = None,
    output_dir: Path | None = None,
    generated_at: str | None = None,
) -> IspyReview:
    """Write JSON and HTML iSpy review reports."""

    payload = build_ispy_review(
        run,
        server_id,
        actions,
        before_state=before_state,
        before_state_path=before_state_path,
        agentdvr_evidence=agentdvr_evidence,
        agentdvr_evidence_path=agentdvr_evidence_path,
        generated_at=generated_at,
    )
    actual_output_dir = output_dir or config.GENERATED_REPORTS_DIR
    actual_output_dir.mkdir(parents=True, exist_ok=True)
    json_path = actual_output_dir / "ispy-review.json"
    html_path = actual_output_dir / "ispy-review.html"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    html_path.write_text(render_ispy_review(payload), encoding="utf-8")
    return IspyReview(payload=payload, json_path=json_path, html_path=html_path)


def render_ispy_review(review: dict[str, Any]) -> str:
    """Render an iSpy review report as HTML."""

    server = review.get("server") if isinstance(review.get("server"), dict) else {}
    body = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>HomeOps iSpy Review</title>",
        "<style>",
        _css(),
        "</style>",
        "</head>",
        "<body>",
        '<main class="shell">',
        '<header class="topbar">',
        "<div>",
        "<h1>HomeOps iSpy Review</h1>",
        f"<p>{escape(str(review.get('server_id', 'unknown')))} generated {escape(str(review.get('generated_at', 'unknown')))}</p>",
        "</div>",
        '<nav class="actions"><a href="index.html">Dashboard</a><a href="ispy-review.json">JSON</a></nav>',
        "</header>",
        _server_panel(server),
        _before_state_panel(_dict(review.get("before_state"))),
        _agentdvr_evidence_panel(_dict(review.get("agentdvr_evidence"))),
        _findings_panel(_list(review.get("findings"))),
        _service_diagnosis_panel(_list(review.get("service_diagnosis"))),
        _reliability_panel(_list(review.get("reliability_checks"))),
        _recommendations_panel(_list(review.get("recommendations"))),
        _actions_panel(_list(review.get("recent_actions"))),
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
    actions: list[history.ActionSummary], server_id: str, limit: int = 10
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
                "expected_approval": _action_record_field(
                    action.record_path, "expected_approval"
                ),
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
        "resources": {
            "cpu_count": _as_int(resources.get("cpu_count")),
            "load_1m": _as_float(resources.get("load_1m")),
            "memory_used_percent": _as_float(resources.get("memory_used_percent")),
            "swap_used_percent": _as_float(resources.get("swap_used_percent")),
        },
        "disk": [
            {
                "mount": str(disk.get("mount") or "unknown"),
                "size_gb": _as_int(disk.get("size_gb")),
                "free_gb": _as_int(disk.get("free_gb")),
                "used_percent": _as_int(disk.get("used_percent")),
            }
            for disk in _list(server.get("disk"))
            if isinstance(disk, dict)
        ],
        "services": _service_summaries(server),
        "security": _dict(server.get("security")),
    }


def _service_summaries(server: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(service.get("name") or "unknown"),
            "state": str(service.get("state") or "unknown"),
            "enabled": bool(service.get("enabled")),
        }
        for service in _list(server.get("services"))
        if isinstance(service, dict)
    ]


def _before_state_summary(
    before_state: dict[str, Any] | None, before_state_path: Path | None
) -> dict[str, Any]:
    if not before_state:
        return {
            "available": False,
            "path": "",
            "intent": "",
            "generated_at": "",
            "eligible_for_rebuild_planning": False,
        }
    readiness = _dict(before_state.get("rebuild_readiness"))
    return {
        "available": True,
        "path": _repo_path(before_state_path) if before_state_path else "",
        "intent": str(before_state.get("intent") or ""),
        "generated_at": str(before_state.get("generated_at") or ""),
        "eligible_for_rebuild_planning": bool(
            readiness.get("eligible_for_rebuild_planning")
        ),
    }


def _agentdvr_evidence_summary(
    evidence: dict[str, Any] | None, evidence_path: Path | None
) -> dict[str, Any]:
    if not evidence:
        return {
            "available": False,
            "path": "",
            "generated_at": "",
            "camera_count": 0,
            "microphone_count": 0,
            "media_total_mb": 0.0,
            "cameras": [],
            "recording_database": {},
        }
    return {
        "available": True,
        "path": _repo_path(evidence_path) if evidence_path else "",
        "generated_at": str(evidence.get("generated_at") or ""),
        "camera_count": _as_int(evidence.get("camera_count")),
        "microphone_count": _as_int(evidence.get("microphone_count")),
        "media_total_mb": _as_float(evidence.get("media_total_mb")),
        "endpoint_checks": _endpoint_checks(evidence),
        "cameras": [
            {
                "id": str(camera.get("id") or ""),
                "name": str(camera.get("name") or ""),
                "directory": str(camera.get("directory") or ""),
                "directory_present": bool(camera.get("directory_present")),
                "resolution": str(camera.get("resolution") or ""),
                "record_on_detect": str(camera.get("record_on_detect") or ""),
                "record_on_alert": str(camera.get("record_on_alert") or ""),
                "alerts_active": str(camera.get("alerts_active") or ""),
                "source_uri_present": bool(camera.get("source_uri_present")),
                "recording_file_count": _as_int(camera.get("recording_file_count")),
                "newest_recording_utc": str(camera.get("newest_recording_utc") or ""),
                "recording_total_mb": _as_float(camera.get("recording_total_mb")),
                "recent_error_count": _as_int(camera.get("recent_error_count")),
                "recent_exception_count": _as_int(camera.get("recent_exception_count")),
                "recording_event_count": _as_int(camera.get("recording_event_count")),
                "recent_log_diagnosis": str(camera.get("recent_log_diagnosis") or ""),
                "endpoint": _endpoint_for_camera(evidence, camera),
            }
            for camera in _list(evidence.get("cameras"))
            if isinstance(camera, dict)
        ],
        "recording_database": _dict(evidence.get("recording_database")),
    }


def _service_diagnosis(server: dict[str, Any]) -> list[dict[str, Any]]:
    services = {item["name"]: item for item in _service_summaries(server)}
    agent = services.get("AgentDVR")
    legacy = services.get("ispy")
    diagnosis: list[dict[str, Any]] = []

    if agent:
        agent_active = str(agent.get("state")) == "active"
        diagnosis.append(
            {
                "status": "ok" if agent_active else "warning",
                "title": "AgentDVR service",
                "detail": (
                    "AgentDVR is active in the latest collection."
                    if agent_active
                    else "AgentDVR is not active in the latest collection."
                ),
                "evidence": agent,
            }
        )
    else:
        diagnosis.append(
            {
                "status": "missing",
                "title": "AgentDVR service",
                "detail": "AgentDVR service was not present in collected service data.",
                "evidence": {},
            }
        )

    if legacy:
        legacy_failed = str(legacy.get("state")) == "failed"
        diagnosis.append(
            {
                "status": "warning" if legacy_failed else "info",
                "title": "Legacy ispy service",
                "detail": (
                    "The enabled legacy ispy.service is failed while AgentDVR is active. "
                    "Read-only inspection found it starts /home/spy/AgentDVR/start_agent.sh; "
                    "that script only calls ./Agent, so the unit is probably stale because "
                    "it lacks the AgentDVR working directory."
                    if legacy_failed and agent and str(agent.get("state")) == "active"
                    else "Legacy ispy.service is present; verify whether it is still needed."
                ),
                "evidence": legacy,
            }
        )
    else:
        diagnosis.append(
            {
                "status": "ok",
                "title": "Legacy ispy service",
                "detail": "No legacy ispy.service was present in collected service data.",
                "evidence": {},
            }
        )
    return diagnosis


def _reliability_checks(
    server: dict[str, Any],
    service_diagnosis: list[dict[str, Any]],
    before_state: dict[str, Any] | None,
    agentdvr_evidence: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    updates = _dict(server.get("updates"))
    disk = _list(server.get("disk"))
    root_disk = next(
        (
            item
            for item in disk
            if isinstance(item, dict) and str(item.get("mount") or "") == "/"
        ),
        {},
    )
    agent_ok = any(
        item.get("title") == "AgentDVR service" and item.get("status") == "ok"
        for item in service_diagnosis
    )
    legacy_warning = any(
        item.get("title") == "Legacy ispy service" and item.get("status") == "warning"
        for item in service_diagnosis
    )
    evidence = _dict(agentdvr_evidence)
    camera_count = _as_int(evidence.get("camera_count"))
    cameras = [
        camera
        for camera in _list(evidence.get("cameras"))
        if isinstance(camera, dict)
    ]
    cameras_with_recordings = [
        camera
        for camera in cameras
        if _as_int(camera.get("recording_file_count")) > 0
        or str(camera.get("newest_recording_utc") or "")
    ]
    missing_camera_dirs = [
        camera
        for camera in cameras
        if not bool(camera.get("directory_present"))
    ]
    endpoint_checks = _endpoint_checks(evidence)
    endpoint_failures = [
        item for item in endpoint_checks if item.get("tcp_reachable") is False
    ]
    endpoint_status = "missing"
    endpoint_detail = (
        "Current collection does not yet report camera connection count or per-camera health."
    )
    if endpoint_checks:
        endpoint_status = "warning" if endpoint_failures else "ok"
        endpoint_detail = (
            f"{len(endpoint_checks) - len(endpoint_failures)} of {len(endpoint_checks)} "
            "camera RTSP endpoints accepted a TCP connection from ispy-server."
        )
    elif camera_count:
        endpoint_status = "partial"
        endpoint_detail = (
            f"AgentDVR config contains {camera_count} cameras, but direct online/offline status is not yet collected."
        )
    return [
        {
            "name": "AgentDVR service active",
            "status": "ok" if agent_ok else "warning",
            "detail": "Collected service state confirms AgentDVR is active."
            if agent_ok
            else "AgentDVR active state needs verification.",
        },
        {
            "name": "Legacy duplicate service",
            "status": "warning" if legacy_warning else "ok",
            "detail": "Failed legacy ispy.service should be cleaned up after approval."
            if legacy_warning
            else "No failed duplicate service is currently flagged.",
        },
        {
            "name": "Security updates",
            "status": "warning" if _as_int(updates.get("pending_security")) else "ok",
            "detail": f"{_as_int(updates.get('pending_security'))} security updates pending.",
        },
        {
            "name": "Reboot requirement",
            "status": "warning" if updates.get("reboot_required") else "ok",
            "detail": "Reboot required."
            if updates.get("reboot_required")
            else "No reboot required in latest collection.",
        },
        {
            "name": "Root disk headroom",
            "status": "ok"
            if _as_int(root_disk.get("used_percent")) < 80
            else "warning",
            "detail": (
                f"Root disk usage is {_as_int(root_disk.get('used_percent'))}% "
                f"with {_as_int(root_disk.get('free_gb'))} GB free."
            ),
        },
        {
            "name": "Before-state captured",
            "status": "ok" if before_state else "missing",
            "detail": "Before-state snapshot exists for AgentDVR reliability work."
            if before_state
            else "Capture before-state before approved cleanup or rebuild planning.",
        },
        {
            "name": "Camera connection evidence",
            "status": endpoint_status,
            "detail": endpoint_detail,
        },
        {
            "name": "Recent recording evidence",
            "status": "warning"
            if camera_count and len(cameras_with_recordings) < camera_count
            else ("ok" if camera_count else "missing"),
            "detail": (
                f"{len(cameras_with_recordings)} of {camera_count} configured cameras have recording database evidence; {len(missing_camera_dirs)} configured camera media directories were not present under the default media path."
                if camera_count
                else "Current collection does not yet report recent recording files or recording freshness."
            ),
        },
    ]


def _recommendations(
    server_id: str,
    server: dict[str, Any],
    findings: list[dict[str, Any]],
    collection_errors: list[dict[str, Any]],
    recent_actions: list[dict[str, Any]],
    before_state: dict[str, Any] | None,
    agentdvr_evidence: dict[str, Any] | None,
    service_diagnosis: list[dict[str, Any]],
    reliability_checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if collection_errors:
        return [
            _recommendation(
                priority=1,
                severity="critical",
                title="Restore iSpy server collection access",
                rationale=str(collection_errors[0].get("message") or "Collection failed."),
                dry_run_command=f"python -m controller.main collect --server {server_id} --dry-run",
            )
        ]

    recommendations: list[dict[str, Any]] = []
    updates = _dict(server.get("updates"))

    if not before_state:
        recommendations.append(
            _recommendation(
                priority=5,
                severity="warning",
                title="Capture before-state before cleanup",
                rationale=(
                    "The iSpy server is rebuildable and this work may lead to "
                    "service cleanup. Capture local evidence before approved changes."
                ),
                dry_run_command=(
                    "python -m controller.main before-state --server "
                    f'{server_id} --intent "before AgentDVR reliability work"'
                ),
            )
        )

    pending_security = _as_int(updates.get("pending_security"))
    if pending_security:
        dry_run = _latest_dry_run(recent_actions, "apply_security_updates")
        recommendations.append(
            _recommendation(
                priority=10,
                severity="warning",
                title="Apply security updates during a camera-safe window",
                rationale=(
                    f"{pending_security} security updates are pending. The dry-run "
                    "path is available; execute only after exact approval and an "
                    "acceptable camera interruption window."
                ),
                action_id="apply_security_updates",
                dry_run_command=(
                    "python -m controller.main actions run apply_security_updates "
                    f"--server {server_id} --dry-run"
                ),
                approval_phrase=str(dry_run.get("expected_approval") or ""),
            )
        )

    if _legacy_service_warning(service_diagnosis):
        recommendations.append(
            _recommendation(
                priority=20,
                severity="warning",
                title="Clean up failed legacy ispy.service",
                rationale=(
                    "AgentDVR.service is active, while the enabled legacy "
                    "ispy.service repeatedly fails through start_agent.sh. Plan "
                    "an approval-gated cleanup to disable the duplicate unit and "
                    "reset failed state after confirming AgentDVR remains healthy."
                ),
                action_id="run_admin_command",
                dry_run_command=(
                    "python -m controller.main actions run run_admin_command "
                    f"--server {server_id} "
                    '--command "systemctl disable --now ispy.service && systemctl reset-failed ispy.service" '
                    '--intent "disable stale duplicate iSpy service" --dry-run'
                ),
            )
        )

    evidence_summary = _agentdvr_evidence_summary(agentdvr_evidence, None)
    if _missing_check(reliability_checks, "Camera connection evidence"):
        recommendations.append(
            _recommendation(
                priority=30,
                severity="info",
                title="Add camera connection evidence",
                rationale=(
                    "Current health collection confirms AgentDVR service state but "
                    "does not report whether cameras are connected. Add a read-only "
                    "AgentDVR/iSpy role check for camera count and offline devices."
                ),
            )
        )
    elif _partial_check(reliability_checks, "Camera connection evidence"):
        recommendations.append(
            _recommendation(
                priority=30,
                severity="info",
                title="Add direct camera online/offline status",
                rationale=(
                    f"AgentDVR config contains {evidence_summary['camera_count']} cameras, "
                    "but the current evidence does not yet prove whether each camera is online."
                ),
            )
        )

    if _missing_check(reliability_checks, "Recent recording evidence"):
        recommendations.append(
            _recommendation(
                priority=40,
                severity="info",
                title="Add recording freshness evidence",
                rationale=(
                    "Current collection does not verify recent recording output. Add "
                    "a check for writable recording paths and recent media activity."
                ),
            )
        )
    elif _warning_check(reliability_checks, "Recent recording evidence"):
        recommendations.append(
            _recommendation(
                priority=40,
                severity="warning",
                title=_recording_recommendation_title(agentdvr_evidence),
                rationale=(
                    _recording_recommendation_rationale(agentdvr_evidence)
                ),
            )
        )

    if updates.get("reboot_required"):
        recommendations.append(
            _recommendation(
                priority=50,
                severity="warning",
                title="Plan a camera-safe reboot",
                rationale="The iSpy server reports that a reboot is required.",
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
                rationale="The latest iSpy findings do not map to a specialized workflow yet.",
            )
        )
    if not recommendations:
        recommendations.append(
            _recommendation(
                priority=100,
                severity="info",
                title="No iSpy remediation needed",
                rationale="No update, service, collection, or reliability issues were found.",
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
    approval_phrase: str | None = None,
) -> dict[str, Any]:
    return {
        "priority": priority,
        "severity": severity,
        "title": title,
        "rationale": rationale,
        "action_id": action_id,
        "dry_run_command": dry_run_command,
        "approval_phrase": approval_phrase,
    }


def _latest_dry_run(actions: list[dict[str, Any]], action_id: str) -> dict[str, Any]:
    for action in actions:
        if str(action.get("action_id") or "") != action_id:
            continue
        if bool(action.get("dry_run")) and str(action.get("status") or "") == "dry_run":
            return action
    return {}


def _legacy_service_warning(service_diagnosis: list[dict[str, Any]]) -> bool:
    return any(
        item.get("title") == "Legacy ispy service" and item.get("status") == "warning"
        for item in service_diagnosis
    )


def _missing_check(checks: list[dict[str, Any]], name: str) -> bool:
    return any(
        item.get("name") == name and item.get("status") == "missing"
        for item in checks
    )


def _partial_check(checks: list[dict[str, Any]], name: str) -> bool:
    return any(
        item.get("name") == name and item.get("status") == "partial"
        for item in checks
    )


def _warning_check(checks: list[dict[str, Any]], name: str) -> bool:
    return any(
        item.get("name") == name and item.get("status") == "warning"
        for item in checks
    )


def _recording_recommendation_title(evidence: dict[str, Any] | None) -> str:
    summary = _agentdvr_evidence_summary(evidence, None)
    for camera in _list(summary.get("cameras")):
        if not isinstance(camera, dict):
            continue
        diagnosis = str(camera.get("recent_log_diagnosis") or "").lower()
        if "connection refused" in diagnosis:
            return "Fix Camera 4 stream connection refusal"
    return "Investigate missing per-camera recording evidence"


def _recording_recommendation_rationale(evidence: dict[str, Any] | None) -> str:
    summary = _agentdvr_evidence_summary(evidence, None)
    for camera in _list(summary.get("cameras")):
        if not isinstance(camera, dict):
            continue
        diagnosis = str(camera.get("recent_log_diagnosis") or "")
        if "connection refused" in diagnosis.lower():
            name = str(camera.get("name") or "A camera")
            return (
                f"{name} has no recording database evidence and recent AgentDVR "
                "logs show FFmpeg OPEN_INPUT connection refused errors. Confirm "
                "the camera is powered, reachable from ispy-server, and serving "
                "the configured stream endpoint."
            )
    return (
        "AgentDVR has recording database evidence for fewer cameras than are "
        "configured. Confirm whether each camera is intended to record and "
        "whether storage paths are correct."
    )


def _endpoint_checks(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    for item in _list(evidence.get("endpoint_checks")):
        if not isinstance(item, dict):
            continue
        checks.append(
            {
                "camera": str(item.get("camera") or ""),
                "host_last_octet": str(item.get("host_last_octet") or ""),
                "protocol": str(item.get("protocol") or ""),
                "port": _as_int(item.get("port")),
                "path_label": str(item.get("path_label") or ""),
                "tcp_reachable": bool(item.get("tcp_reachable")),
                "tcp_error": str(item.get("tcp_error") or ""),
                "rtsp_options_status": str(item.get("rtsp_options_status") or ""),
            }
        )
    return checks


def _endpoint_for_camera(
    evidence: dict[str, Any], camera: dict[str, Any]
) -> dict[str, Any]:
    camera_name = str(camera.get("name") or "")
    for item in _endpoint_checks(evidence):
        if item.get("camera") == camera_name:
            return item
    return {}


def _server_panel(server: dict[str, Any]) -> str:
    updates = _dict(server.get("updates"))
    resources = _dict(server.get("resources"))
    return (
        '<section class="panel">'
        "<h2>Server State</h2>"
        '<dl class="facts">'
        f"<div><dt>Hostname</dt><dd>{escape(str(server.get('hostname', 'unknown')))}</dd></div>"
        f"<div><dt>Collected</dt><dd>{escape(str(server.get('collected_at', '')))}</dd></div>"
        f"<div><dt>Updates</dt><dd>{updates.get('pending_total', 0)}</dd></div>"
        f"<div><dt>Security Updates</dt><dd>{updates.get('pending_security', 0)}</dd></div>"
        f"<div><dt>Reboot</dt><dd>{'yes' if updates.get('reboot_required') else 'no'}</dd></div>"
        f"<div><dt>Memory</dt><dd>{resources.get('memory_used_percent', 0)}%</dd></div>"
        "</dl>"
        "</section>"
    )


def _before_state_panel(before_state: dict[str, Any]) -> str:
    if not before_state.get("available"):
        return (
            '<section class="panel"><h2>Before-State</h2>'
            "<p>No before-state snapshot is attached to this report.</p></section>"
        )
    eligible = "yes" if before_state.get("eligible_for_rebuild_planning") else "no"
    return (
        '<section class="panel">'
        "<h2>Before-State</h2>"
        '<dl class="facts facts-four">'
        f"<div><dt>Generated</dt><dd>{escape(str(before_state.get('generated_at', '')))}</dd></div>"
        f"<div><dt>Intent</dt><dd>{escape(str(before_state.get('intent', '')))}</dd></div>"
        f"<div><dt>Rebuild Planning</dt><dd>{eligible}</dd></div>"
        f"<div><dt>Path</dt><dd><code>{escape(str(before_state.get('path', '')))}</code></dd></div>"
        "</dl>"
        "</section>"
    )


def _agentdvr_evidence_panel(evidence: dict[str, Any]) -> str:
    if not evidence.get("available"):
        return (
            '<section class="panel"><h2>AgentDVR Evidence</h2>'
            "<p>No AgentDVR inspection evidence is attached to this report.</p></section>"
        )
    camera_rows = []
    for camera in _list(evidence.get("cameras")):
        if not isinstance(camera, dict):
            continue
        camera_rows.append(
            "<tr>"
            f"<td>{escape(str(camera.get('id', '')))}</td>"
            f"<td>{escape(str(camera.get('name', '')))}</td>"
            f"<td>{escape(str(camera.get('resolution', '')))}</td>"
            f"<td>{'yes' if camera.get('source_uri_present') else 'no'}</td>"
            f"<td>{_endpoint_cell(_dict(camera.get('endpoint')))}</td>"
            f"<td>{'yes' if camera.get('directory_present') else 'no'}</td>"
            f"<td>{escape(str(camera.get('recording_file_count', 0)))}</td>"
            f"<td>{escape(str(camera.get('newest_recording_utc', '')))}</td>"
            f"<td>{escape(str(camera.get('recent_error_count', 0)))}</td>"
            f"<td>{escape(str(camera.get('recent_log_diagnosis', '')))}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>AgentDVR Evidence</h2>"
        '<dl class="facts facts-four">'
        f"<div><dt>Generated</dt><dd>{escape(str(evidence.get('generated_at', '')))}</dd></div>"
        f"<div><dt>Cameras</dt><dd>{escape(str(evidence.get('camera_count', 0)))}</dd></div>"
        f"<div><dt>Microphones</dt><dd>{escape(str(evidence.get('microphone_count', 0)))}</dd></div>"
        f"<div><dt>Media Size</dt><dd>{escape(str(evidence.get('media_total_mb', 0)))} MB</dd></div>"
        "</dl>"
        "<h3>Configured Cameras</h3>"
        '<table><thead><tr><th>ID</th><th>Name</th><th>Resolution</th><th>Source URI Present</th><th>Endpoint</th><th>Media Dir Present</th><th>DB Files</th><th>Newest Recording</th><th>Recent Errors</th><th>Log Diagnosis</th></tr></thead><tbody>'
        + "".join(camera_rows)
        + "</tbody></table>"
        "</section>"
    )


def _endpoint_cell(endpoint: dict[str, Any]) -> str:
    if not endpoint:
        return "not checked"
    status = "reachable" if endpoint.get("tcp_reachable") else "refused"
    host = endpoint.get("host_last_octet") or "?"
    port = endpoint.get("port") or ""
    path = endpoint.get("path_label") or ""
    rtsp_status = endpoint.get("rtsp_options_status") or ""
    detail = escape(f"host .{host}:{port}{path}")
    if rtsp_status:
        detail += f"<br><small>{escape(str(rtsp_status))}</small>"
    return f"{_badge('ok' if status == 'reachable' else 'warning')}<br>{detail}"


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


def _service_diagnosis_panel(items: list[Any]) -> str:
    return _status_table(
        "Service Diagnosis",
        ["Status", "Item", "Detail"],
        [
            [
                _badge(str(item.get("status") or "info")),
                escape(str(item.get("title") or "")),
                escape(str(item.get("detail") or "")),
            ]
            for item in items
            if isinstance(item, dict)
        ],
    )


def _reliability_panel(items: list[Any]) -> str:
    return _status_table(
        "Camera Reliability Checklist",
        ["Status", "Check", "Detail"],
        [
            [
                _badge(str(item.get("status") or "info")),
                escape(str(item.get("name") or "")),
                escape(str(item.get("detail") or "")),
            ]
            for item in items
            if isinstance(item, dict)
        ],
    )


def _recommendations_panel(recommendations: list[Any]) -> str:
    rows = []
    for item in recommendations:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "info")
        command = str(item.get("dry_run_command") or "")
        approval = str(item.get("approval_phrase") or "")
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('priority', '')))}</td>"
            f"<td>{_badge(severity)}</td>"
            f"<td><strong>{escape(str(item.get('title', '')))}</strong><br>{escape(str(item.get('rationale', '')))}</td>"
            f"<td><code>{escape(str(item.get('action_id') or 'none'))}</code></td>"
            f"<td>{'<code>' + escape(command) + '</code>' if command else 'none'}"
            f"{'<br><small>Approval: <code>' + escape(approval) + '</code></small>' if approval else ''}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>Recommended Next Steps</h2>"
        '<table><thead><tr><th>Priority</th><th>Severity</th><th>Recommendation</th><th>Action</th><th>Dry Run</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></section>"
    )


def _actions_panel(actions: list[Any]) -> str:
    rows = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(str(action.get('timestamp', '')))}</td>"
            f"<td><code>{escape(str(action.get('action_id', '')))}</code></td>"
            f"<td>{escape(str(action.get('status', '')))}</td>"
            f"<td>{'yes' if action.get('dry_run') else 'no'}</td>"
            f"<td><code>{escape(str(action.get('record_path', '')))}</code></td>"
            "</tr>"
        )
    if not rows:
        return '<section class="panel"><h2>Recent Actions</h2><p>No recent actions for this server.</p></section>'
    return (
        '<section class="panel">'
        "<h2>Recent Actions</h2>"
        '<table><thead><tr><th>Timestamp</th><th>Action</th><th>Status</th><th>Dry Run</th><th>Record</th></tr></thead><tbody>'
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


def _status_table(title: str, headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return f'<section class="panel"><h2>{escape(title)}</h2><p>No data.</p></section>'
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    row_html = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return (
        '<section class="panel">'
        f"<h2>{escape(title)}</h2>"
        f"<table><thead><tr>{header_html}</tr></thead><tbody>{row_html}</tbody></table>"
        "</section>"
    )


def _badge(status: str) -> str:
    normalized = (
        status
        if status in {"critical", "warning", "info", "ok", "missing", "partial"}
        else "info"
    )
    return (
        f'<span class="badge badge-{escape(normalized)}">'
        f"{escape(normalized)}</span>"
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


def _repo_path(path: Path | None) -> str:
    if path is None:
        return ""
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
  --ok: #16794c;
  --missing: #53616f;
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
p, td, th, li, dd, dt, small { font-size: 14px; }
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
.facts-four { grid-template-columns: repeat(4, minmax(0, 1fr)); }
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
.badge-ok { background: #e9f8f1; color: var(--ok); }
.badge-missing { background: #eef2f6; color: var(--missing); }
.badge-partial { background: #e8f3f7; color: var(--accent); }
@media (max-width: 920px) {
  .topbar { display: block; }
  .actions { margin-top: 10px; }
  .facts, .facts-four { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .facts, .facts-four { grid-template-columns: 1fr; }
}
"""
