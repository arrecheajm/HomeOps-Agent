"""Markdown report rendering for HomeOps fleet health data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import config, rules


ROLE_LABELS = {
    "openvpn_server": "VPN",
    "vpn": "VPN",
    "ispy_server": "Security Cameras",
    "security_camera": "Security Cameras",
    "container_host": "Containers",
}


def write_report(fleet: dict[str, Any], output_dir: Path) -> Path:
    """Render and write a Markdown report."""

    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = str(fleet.get("generated_at") or config.utc_now_iso())
    filename = f"homeops-report-{config.safe_timestamp(generated_at)}.md"
    report_path = output_dir / filename
    report_path.write_text(render_report(fleet), encoding="utf-8")
    return report_path


def render_report(fleet: dict[str, Any]) -> str:
    generated_at = str(fleet.get("generated_at") or config.utc_now_iso())
    findings = list(fleet.get("findings") or [])
    counts = rules.count_by_severity(findings)

    lines: list[str] = [
        "# HomeOps Maintenance Report",
        "",
        f"Generated: {generated_at}",
        "",
        "## Fleet Summary",
        "",
        (
            f"{fleet.get('servers_checked', 0)} servers checked. "
            f"{_plural(counts['critical'], 'critical finding')}. "
            f"{_plural(counts['warning'], 'warning')}. "
            f"{_plural(counts['info'], 'informational note')}."
        ),
        "",
    ]

    lines.extend(_server_table(fleet, findings))
    lines.append("")
    lines.extend(_findings_section("Critical Findings", findings, "critical"))
    lines.append("")
    lines.extend(_findings_section("Warnings", findings, "warning"))
    lines.append("")
    lines.extend(_findings_section("Informational Notes", findings, "info"))
    lines.append("")
    lines.extend(_next_steps(findings))
    lines.append("")
    lines.extend(["## Actions Taken", "", "No actions executed."])

    return "\n".join(lines) + "\n"


def _server_table(fleet: dict[str, Any], findings: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Server | Role | Status | Notes |",
        "|---|---|---|---|",
    ]

    findings_by_server: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        findings_by_server.setdefault(str(finding.get("server_id", "unknown")), []).append(
            finding
        )

    for server in fleet.get("servers") or []:
        server_id = str(server.get("server_id") or server.get("hostname") or "unknown")
        role = ROLE_LABELS.get(str(server.get("role")), str(server.get("role") or "Unknown"))
        server_findings = findings_by_server.get(server_id, [])
        status = _server_status(server_findings)
        note = _server_note(server_findings)
        lines.append(
            f"| `{_escape(server_id)}` | {_escape(role)} | {status} | {_escape(note)} |"
        )

    if not fleet.get("servers"):
        lines.append("| none | none | Unknown | No server data available |")

    return lines


def _findings_section(
    title: str, findings: list[dict[str, Any]], severity: str
) -> list[str]:
    matching = [finding for finding in findings if finding.get("severity") == severity]
    lines = [f"## {title}", ""]
    if not matching:
        lines.append(f"No {title.lower()}.")
        return lines

    for finding in matching:
        lines.extend(
            [
                f"### {_escape(str(finding.get('title') or finding.get('code')))}",
                "",
                f"Server: `{_escape(str(finding.get('server_id', 'unknown')))}`",
                "",
                _escape(str(finding.get("message", ""))),
                "",
            ]
        )
        action_ids = finding.get("recommended_action_ids") or []
        if action_ids:
            joined = ", ".join(f"`{_escape(str(action_id))}`" for action_id in action_ids)
            lines.extend([f"Recommended action IDs: {joined}", ""])
        else:
            lines.extend(["Recommended action IDs: none.", ""])

    return lines


def _next_steps(findings: list[dict[str, Any]]) -> list[str]:
    lines = ["## Suggested Next Steps", ""]
    if not findings:
        lines.append("1. Re-run collection on the next maintenance interval.")
        return lines

    for index, finding in enumerate(findings, start=1):
        action_ids = finding.get("recommended_action_ids") or []
        if action_ids:
            action_text = ", ".join(f"`{_escape(str(action_id))}`" for action_id in action_ids)
            lines.append(
                f"{index}. Review `{_escape(str(finding.get('server_id', 'unknown')))}` "
                f"finding `{_escape(str(finding.get('code', 'unknown')))}` and consider {action_text}."
            )
        else:
            lines.append(
                f"{index}. Review `{_escape(str(finding.get('server_id', 'unknown')))}` "
                f"finding `{_escape(str(finding.get('code', 'unknown')))}`."
            )
    return lines


def _server_status(findings: list[dict[str, Any]]) -> str:
    worst = rules.worst_severity(findings)
    if worst == "critical":
        return "Critical"
    if worst == "warning":
        return "Warning"
    if worst == "info":
        return "Info"
    return "OK"


def _server_note(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "No issues detected"
    return str(findings[0].get("message") or findings[0].get("title") or "Review finding")


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _plural(count: int, label: str) -> str:
    if count == 1:
        return f"1 {label}"
    return f"{count} {label}s"
