"""Local rule checks for HomeOps fleet health data."""

from __future__ import annotations

from typing import Any


SEVERITY_RANK = {"critical": 3, "warning": 2, "info": 1}


def evaluate_fleet(fleet: dict[str, Any]) -> list[dict[str, Any]]:
    """Evaluate local rules and return normalized finding objects."""

    findings: list[dict[str, Any]] = []

    for error in fleet.get("collection_errors") or []:
        findings.append(
            _finding(
                server_id=str(error.get("server_id", "unknown")),
                severity="critical",
                code="collection_failed",
                title="Collection failed",
                message=str(error.get("message", "Server collection failed.")),
                evidence=error,
                recommended_action_ids=[],
            )
        )

    for server in fleet.get("servers") or []:
        findings.extend(_evaluate_server(server))

    return sorted(
        findings,
        key=lambda finding: (
            -SEVERITY_RANK.get(str(finding.get("severity")), 0),
            str(finding.get("server_id", "")),
            str(finding.get("code", "")),
        ),
    )


def count_by_severity(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"critical": 0, "warning": 0, "info": 0}
    for finding in findings:
        severity = str(finding.get("severity", "info"))
        if severity in counts:
            counts[severity] += 1
    return counts


def worst_severity(findings: list[dict[str, Any]]) -> str | None:
    worst: str | None = None
    for finding in findings:
        severity = str(finding.get("severity", "info"))
        if SEVERITY_RANK.get(severity, 0) > SEVERITY_RANK.get(worst or "", 0):
            worst = severity
    return worst


def _evaluate_server(server: dict[str, Any]) -> list[dict[str, Any]]:
    server_id = str(server.get("server_id") or server.get("hostname") or "unknown")
    findings: list[dict[str, Any]] = []

    findings.extend(_disk_findings(server_id, server.get("disk") or []))
    findings.extend(_service_findings(server_id, server.get("services") or []))
    findings.extend(_update_findings(server_id, server.get("updates") or {}))
    findings.extend(_docker_findings(server_id, server.get("docker") or {}))
    findings.extend(_security_findings(server_id, server.get("security") or {}))

    return findings


def _disk_findings(server_id: str, disks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for disk in disks:
        used_percent = _as_float(disk.get("used_percent"))
        if used_percent is None:
            continue

        mount = str(disk.get("mount") or "unknown")
        if used_percent >= 95:
            findings.append(
                _finding(
                    server_id,
                    "critical",
                    "disk_usage_critical",
                    "Disk usage is critical",
                    f"Mount {mount} is {used_percent:g}% full.",
                    {"mount": mount, "used_percent": used_percent},
                    [],
                )
            )
        elif used_percent >= 80:
            findings.append(
                _finding(
                    server_id,
                    "warning",
                    "disk_usage_high",
                    "Disk usage is high",
                    f"Mount {mount} is {used_percent:g}% full.",
                    {"mount": mount, "used_percent": used_percent},
                    [],
                )
            )
    return findings


def _service_findings(
    server_id: str, services: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    findings = []
    for service in services:
        state = str(service.get("state") or "unknown")
        if state == "active":
            continue

        service_name = str(service.get("name") or "unknown")
        findings.append(
            _finding(
                server_id,
                "warning",
                "service_failed",
                "Service is not active",
                f"Service {service_name} is {state}.",
                {"service": service_name, "state": state},
                ["restart_service"],
            )
        )
    return findings


def _update_findings(server_id: str, updates: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    pending_security = _as_int(updates.get("pending_security")) or 0
    pending_total = _as_int(updates.get("pending_total")) or 0
    reboot_required = bool(updates.get("reboot_required"))

    if pending_security > 0:
        findings.append(
            _finding(
                server_id,
                "warning",
                "security_updates_pending",
                "Security updates are pending",
                _pending_message(pending_security, "security update"),
                {"pending_security": pending_security},
                ["apply_security_updates"],
            )
        )
    elif pending_total > 0:
        findings.append(
            _finding(
                server_id,
                "info",
                "updates_pending",
                "Package updates are pending",
                _pending_message(pending_total, "package update"),
                {"pending_total": pending_total},
                [],
            )
        )

    if reboot_required:
        findings.append(
            _finding(
                server_id,
                "warning",
                "reboot_required",
                "Reboot is required",
                "The server reports that a reboot is required.",
                {"reboot_required": True},
                ["reboot_server"],
            )
        )

    return findings


def _docker_findings(server_id: str, docker: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    if not docker.get("installed"):
        return findings

    for container in docker.get("unhealthy") or []:
        container_name = str(container.get("name") or "unknown")
        status = str(container.get("status") or "unhealthy")
        findings.append(
            _finding(
                server_id,
                "warning",
                "docker_unhealthy_container",
                "Docker container is unhealthy",
                f"Container {container_name} is reporting {status}.",
                {"container": container_name, "status": status},
                ["restart_docker_container"],
            )
        )

    expected_stopped = docker.get("expected_stopped") or []
    for container in expected_stopped:
        container_name = str(container.get("name") or "unknown")
        status = str(container.get("status") or "stopped")
        findings.append(
            _finding(
                server_id,
                "warning",
                "docker_container_stopped",
                "Expected Docker container is stopped",
                f"Expected container {container_name} is {status}.",
                {"container": container_name, "status": status},
                ["restart_docker_container"],
            )
        )

    return findings


def _security_findings(server_id: str, security: dict[str, Any]) -> list[dict[str, Any]]:
    failed_logins = _as_int(security.get("failed_ssh_logins_24h")) or 0
    if failed_logins >= 100:
        return [
            _finding(
                server_id,
                "critical",
                "ssh_failed_login_spike",
                "SSH failed login spike",
                f"{failed_logins} failed SSH logins were reported in the last 24 hours.",
                {"failed_ssh_logins_24h": failed_logins},
                [],
            )
        ]
    if failed_logins >= 20:
        return [
            _finding(
                server_id,
                "warning",
                "ssh_failed_login_spike",
                "SSH failed login spike",
                f"{failed_logins} failed SSH logins were reported in the last 24 hours.",
                {"failed_ssh_logins_24h": failed_logins},
                [],
            )
        ]
    return []


def _finding(
    server_id: str,
    severity: str,
    code: str,
    title: str,
    message: str,
    evidence: dict[str, Any],
    recommended_action_ids: list[str],
) -> dict[str, Any]:
    return {
        "server_id": server_id,
        "severity": severity,
        "code": code,
        "title": title,
        "message": message,
        "evidence": evidence,
        "recommended_action_ids": recommended_action_ids,
    }


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pending_message(count: int, label: str) -> str:
    if count == 1:
        return f"1 {label} is pending."
    return f"{count} {label}s are pending."
