"""HTML dashboard rendering for HomeOps run history."""

from __future__ import annotations

import os
from html import escape
from pathlib import Path
from typing import Any

from . import config, history, rules


ROLE_LABELS = {
    "openvpn_server": "VPN",
    "vpn": "VPN",
    "ispy_server": "Security Cameras",
    "security_camera": "Security Cameras",
    "container_host": "Containers",
}


def write_dashboard(
    runs: list[history.RunSummary],
    output_dir: Path | None = None,
    actions: list[history.ActionSummary] | None = None,
) -> Path:
    """Render and write the HTML dashboard."""

    actual_output_dir = output_dir or config.GENERATED_REPORTS_DIR
    actual_output_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = actual_output_dir / "index.html"
    dashboard_path.write_text(
        render_dashboard(runs, actual_output_dir, actions),
        encoding="utf-8",
    )
    return dashboard_path


def render_dashboard(
    runs: list[history.RunSummary],
    output_dir: Path | None = None,
    actions: list[history.ActionSummary] | None = None,
) -> str:
    """Render an HTML dashboard for the available run history."""

    actual_output_dir = output_dir or config.GENERATED_REPORTS_DIR
    sorted_runs = sorted(runs, key=lambda run: run.generated_dt, reverse=True)
    latest = sorted_runs[0] if sorted_runs else None
    generated_at = config.utc_now_iso()

    body: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>HomeOps Dashboard</title>",
        "<style>",
        _css(),
        "</style>",
        "</head>",
        "<body>",
        '<main class="shell">',
        '<header class="topbar">',
        "<div>",
        "<h1>HomeOps Dashboard</h1>",
        f"<p>Generated {escape(generated_at)}</p>",
        "</div>",
        _latest_link(latest, actual_output_dir),
        "</header>",
    ]

    if not latest:
        body.extend(
            [
                '<section class="empty">',
                "<h2>No Runs Found</h2>",
                "<p>Run <code>python -m controller.main collect</code> to create the first dashboard entry.</p>",
                "</section>",
                "</main>",
                "</body>",
                "</html>",
            ]
        )
        return "\n".join(body) + "\n"

    body.extend(_dashboard_nav())
    body.append('<section id="overview" class="view-section">')
    body.extend(_summary_cards(latest))
    body.extend(_server_section(latest))
    body.extend(_findings_section(latest))
    body.extend(_actions_section(actions or [], actual_output_dir))
    body.append("</section>")
    body.extend(_history_section(sorted_runs))
    body.extend(_timeline_section(sorted_runs, actual_output_dir))
    body.extend(["</main>", "</body>", "</html>"])
    return "\n".join(body) + "\n"


def _dashboard_nav() -> list[str]:
    return [
        '<nav class="tabbar" aria-label="Dashboard views">',
        '<a href="#overview">Overview</a>',
        '<a href="#history">Historical Data</a>',
        '<a href="#runs">Run Timeline</a>',
        "</nav>",
    ]


def _latest_link(run: history.RunSummary | None, output_dir: Path) -> str:
    if not run:
        return ""
    return f'<nav class="actions">{_link("Fleet JSON", run.fleet_path, output_dir)}</nav>'


def _summary_cards(run: history.RunSummary) -> list[str]:
    total_findings = sum(run.counts.values())
    return [
        '<section class="summary-grid" aria-label="Latest run summary">',
        _metric_card("Latest Run", _display_time(run), run.run_id),
        _metric_card("Servers", str(run.servers_checked), f"{run.servers_failed} failed"),
        _metric_card("Critical", str(run.counts["critical"]), "Immediate attention"),
        _metric_card("Warnings", str(run.counts["warning"]), f"{total_findings} total findings"),
        _metric_card("Info", str(run.counts["info"]), "Maintenance notes"),
        "</section>",
    ]


def _metric_card(title: str, value: str, detail: str) -> str:
    return (
        '<article class="metric">'
        f"<span>{escape(title)}</span>"
        f"<strong>{escape(value)}</strong>"
        f"<small>{escape(detail)}</small>"
        "</article>"
    )


def _server_section(run: history.RunSummary) -> list[str]:
    findings_by_server: dict[str, list[dict[str, Any]]] = {}
    for finding in run.findings:
        server_id = str(finding.get("server_id", "unknown"))
        findings_by_server.setdefault(server_id, []).append(finding)

    lines = [
        '<section class="panel">',
        "<h2>Latest Server State</h2>",
        '<div class="server-grid">',
    ]
    for server in run.servers:
        server_id = str(server.get("server_id") or server.get("hostname") or "unknown")
        role = ROLE_LABELS.get(str(server.get("role")), str(server.get("role") or "Unknown"))
        status = _server_status(findings_by_server.get(server_id, []))
        note = _server_note(findings_by_server.get(server_id, []))
        hostname = str(server.get("hostname") or "unknown")
        updates = server.get("updates") if isinstance(server.get("updates"), dict) else {}
        pending_total = updates.get("pending_total", 0)
        reboot_required = "yes" if updates.get("reboot_required") else "no"
        services = _server_services(server)
        lines.extend(
            [
                f'<article class="server-card status-{status.lower()}">',
                f"<h3>{escape(server_id)}</h3>",
                f"<p>{escape(role)} on <code>{escape(hostname)}</code></p>",
                '<dl class="server-facts">',
                f"<div><dt>Status</dt><dd>{escape(status)}</dd></div>",
                f"<div><dt>Updates</dt><dd>{escape(str(pending_total))}</dd></div>",
                f"<div><dt>Reboot</dt><dd>{escape(reboot_required)}</dd></div>",
                "</dl>",
                '<div class="service-block">',
                "<h4>Services</h4>",
                _service_list(services),
                "</div>",
                f"<p>{escape(note)}</p>",
                "</article>",
            ]
        )
    lines.extend(["</div>", "</section>"])
    return lines


def _findings_section(run: history.RunSummary) -> list[str]:
    lines = ['<section class="panel">', "<h2>Latest Findings</h2>"]
    if not run.findings:
        lines.extend(["<p>No findings in the latest run.</p>", "</section>"])
        return lines

    lines.extend(
        [
            '<table class="findings-table">',
            "<thead><tr><th>Severity</th><th>Server</th><th>Code</th><th>Message</th><th>Actions</th></tr></thead>",
            "<tbody>",
        ]
    )
    for finding in sorted(
        run.findings,
        key=lambda item: (
            -rules.SEVERITY_RANK.get(str(item.get("severity")), 0),
            str(item.get("server_id", "")),
            str(item.get("code", "")),
        ),
    ):
        action_ids = finding.get("recommended_action_ids") or []
        actions = ", ".join(str(action_id) for action_id in action_ids) or "none"
        severity = str(finding.get("severity", "info"))
        lines.append(
            "<tr>"
            f'<td><span class="badge badge-{escape(severity)}">{escape(severity)}</span></td>'
            f"<td>{escape(str(finding.get('server_id', 'unknown')))}</td>"
            f"<td><code>{escape(str(finding.get('code', 'unknown')))}</code></td>"
            f"<td>{escape(str(finding.get('message', '')))}</td>"
            f"<td>{escape(actions)}</td>"
            "</tr>"
        )
    lines.extend(["</tbody>", "</table>", "</section>"])
    return lines


def _actions_section(
    actions: list[history.ActionSummary], output_dir: Path
) -> list[str]:
    lines = ['<section class="panel">', "<h2>Action History</h2>"]
    recent_actions = sorted(actions, key=lambda action: action.timestamp_dt, reverse=True)[
        :10
    ]
    if not recent_actions:
        lines.extend(["<p>No action attempts recorded.</p>", "</section>"])
        return lines

    lines.extend(
        [
            '<table class="actions-table">',
            "<thead><tr><th>Time</th><th>Server</th><th>Action</th><th>Status</th><th>Arguments</th><th>Record</th></tr></thead>",
            "<tbody>",
        ]
    )
    for action in recent_actions:
        status = _action_status_label(action)
        lines.append(
            "<tr>"
            f"<td>{escape(_display_action_time(action))}</td>"
            f"<td>{escape(action.server_id)}</td>"
            f"<td><code>{escape(action.action_id)}</code></td>"
            f'<td><span class="badge badge-action-{escape(status)}">{escape(status)}</span></td>'
            f"<td>{escape(_format_arguments(action.arguments))}</td>"
            f"<td>{_link('JSON', action.record_path, output_dir)}</td>"
            "</tr>"
        )
    lines.extend(["</tbody>", "</table>", "</section>"])
    return lines


def _server_services(server: dict[str, Any]) -> list[dict[str, Any]]:
    services = server.get("services")
    if not isinstance(services, list):
        return []

    role = str(server.get("role") or "")
    priority = {
        "openvpn_server": ("openvpnas", "openvpn", "openvpn-server@server", "ssh"),
        "ispy_server": ("AgentDVR", "ispy", "agent-dvr", "ssh"),
        "container_host": ("docker", "ssh"),
    }.get(role, ("ssh",))

    def sort_key(service: dict[str, Any]) -> tuple[int, str]:
        name = str(service.get("name") or "")
        try:
            rank = priority.index(name)
        except ValueError:
            rank = len(priority)
        return (rank, name.lower())

    return sorted(
        [service for service in services if isinstance(service, dict)],
        key=sort_key,
    )


def _service_list(services: list[dict[str, Any]]) -> str:
    if not services:
        return '<p class="muted">No services reported.</p>'

    items = []
    for service in services:
        name = str(service.get("name") or "unknown")
        state = str(service.get("state") or "unknown")
        enabled = service.get("enabled")
        enabled_text = "enabled" if enabled is True else "disabled"
        if enabled is None:
            enabled_text = "unknown"
        state_class = "ok" if state == "active" else "bad"
        items.append(
            '<li class="service-row">'
            f"<code>{escape(name)}</code>"
            f'<span class="service-state service-{state_class}">{escape(state)}</span>'
            f"<small>{escape(enabled_text)}</small>"
            "</li>"
        )
    return f'<ul class="service-list">{"".join(items)}</ul>'


def _history_section(runs: list[history.RunSummary]) -> list[str]:
    chart_runs = list(reversed(runs[:12]))
    run_label = "1 run" if len(chart_runs) == 1 else f"{len(chart_runs)} runs"
    lines = [
        '<section id="history" class="panel view-section">',
        '<div class="section-heading">',
        "<h2>Historical Data</h2>",
        f'<span>{escape(run_label)}</span>',
        "</div>",
        '<div class="chart-grid">',
        '<section class="chart-block chart-block-wide">',
        "<h3>Finding Trend</h3>",
        _finding_trend_chart(chart_runs),
        _chart_legend(
            [
                ("Critical", "#b42318"),
                ("Warnings", "#9a5b00"),
                ("Info", "#2d6cdf"),
            ]
        ),
        "</section>",
        '<section class="chart-block chart-block-wide">',
        "<h3>Pending Updates</h3>",
        _updates_chart(chart_runs),
        "</section>",
        '<section class="chart-block chart-block-wide">',
        "<h3>Reboot And Docker Watch</h3>",
        _operations_chart(chart_runs),
        _chart_legend(
            [
                ("Reboot required", "#9a5b00"),
                ("Docker issues", "#31686f"),
            ]
        ),
        "</section>",
        "</div>",
        "</section>",
    ]
    return lines


def _timeline_section(runs: list[history.RunSummary], output_dir: Path) -> list[str]:
    lines = ['<section id="runs" class="panel view-section">', "<h2>Run Timeline</h2>"]
    for label, grouped_runs in history.group_runs_by_period(runs):
        lines.extend([f"<h3>{escape(label)}</h3>", '<div class="timeline">'])
        for run in grouped_runs:
            links = [_link("JSON", run.fleet_path, output_dir)]
            lines.append(
                '<article class="timeline-row">'
                "<div>"
                f"<strong>{escape(_display_time(run))}</strong>"
                f"<span>{escape(run.run_id)}</span>"
                "</div>"
                f"<p>{run.servers_checked} servers, {run.servers_failed} failed, "
                f"{run.counts['critical']} critical, {run.counts['warning']} warning, "
                f"{run.counts['info']} info</p>"
                f'<nav>{"".join(links)}</nav>'
                "</article>"
            )
        lines.append("</div>")
    lines.append("</section>")
    return lines


def _finding_trend_chart(runs: list[history.RunSummary]) -> str:
    metrics = [_run_metrics(run) for run in runs]
    max_value = max(
        1,
        *[
            item["critical"] + item["warning"] + item["info"]
            for item in metrics
        ],
    )
    width, height = 760, 260
    left, right, top, bottom = 44, 18, 14, 46
    chart_width = width - left - right
    chart_height = height - top - bottom
    bars: list[str] = []
    count = max(1, len(metrics))
    step = chart_width / count
    bar_width = max(12, min(34, step * 0.62))
    colors = (("info", "#2d6cdf"), ("warning", "#9a5b00"), ("critical", "#b42318"))

    for index, item in enumerate(metrics):
        x = left + (index * step) + ((step - bar_width) / 2)
        y_cursor = top + chart_height
        for key, color in colors:
            value = item[key]
            if value <= 0:
                continue
            bar_height = (value / max_value) * chart_height
            y_cursor -= bar_height
            bars.append(
                f'<rect x="{x:.1f}" y="{y_cursor:.1f}" width="{bar_width:.1f}" '
                f'height="{bar_height:.1f}" fill="{color}" rx="3">'
                f"<title>{escape(item['label'])}: {value} {key}</title>"
                "</rect>"
            )

    return _svg_chart(
        width,
        height,
        _grid_lines(max_value, left, top, chart_width, chart_height)
        + bars
        + _bar_x_labels(metrics, left, top, chart_width, chart_height)
        + _axis_line(left, top, chart_width, chart_height),
    )


def _updates_chart(runs: list[history.RunSummary]) -> str:
    metrics = [_run_metrics(run) for run in runs]
    server_ids = _ordered_server_ids(runs)
    values = [
        item["updates_by_server"].get(server_id)
        for item in metrics
        for server_id in server_ids
        if item["updates_by_server"].get(server_id) is not None
    ]
    max_value = max(1, *values) if values else 1
    width, height = 760, 280
    left, right, top, bottom = 44, 28, 14, 58
    chart_width = width - left - right
    chart_height = height - top - bottom
    palette = ("#2d6cdf", "#1f7a4d", "#9a5b00", "#b42318", "#31686f")
    series: list[str] = []

    for index, server_id in enumerate(server_ids):
        color = palette[index % len(palette)]
        points: list[tuple[float, float, int, str]] = []
        for run_index, item in enumerate(metrics):
            value = item["updates_by_server"].get(server_id)
            if value is None:
                continue
            x = _x_position(run_index, len(metrics), left, chart_width)
            y = _y_position(value, max_value, top, chart_height)
            points.append((x, y, value, item["label"]))

        for path in _line_paths(points):
            series.append(
                f'<path d="{path}" fill="none" stroke="{color}" '
                'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />'
            )
        for x, y, value, label in points:
            series.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}">'
                f"<title>{escape(server_id)} {escape(label)}: {value} updates</title>"
                "</circle>"
            )

    legend = _chart_legend(
        [(server_id, palette[index % len(palette)]) for index, server_id in enumerate(server_ids)]
    )
    return (
        _svg_chart(
            width,
            height,
            _grid_lines(max_value, left, top, chart_width, chart_height)
            + series
            + _x_labels(metrics, left, top, chart_width, chart_height)
            + _axis_line(left, top, chart_width, chart_height),
        )
        + legend
    )


def _operations_chart(runs: list[history.RunSummary]) -> str:
    metrics = [_run_metrics(run) for run in runs]
    max_value = max(
        1,
        *[
            max(item["reboot_required"], item["docker_issues"])
            for item in metrics
        ],
    )
    width, height = 760, 260
    left, right, top, bottom = 44, 18, 14, 46
    chart_width = width - left - right
    chart_height = height - top - bottom
    count = max(1, len(metrics))
    step = chart_width / count
    bar_width = max(8, min(18, step * 0.28))
    bars: list[str] = []

    for index, item in enumerate(metrics):
        center = left + (index * step) + (step / 2)
        for offset, key, color in (
            (-bar_width * 0.6, "reboot_required", "#9a5b00"),
            (bar_width * 0.6, "docker_issues", "#31686f"),
        ):
            value = item[key]
            if value <= 0:
                continue
            height_value = (value / max_value) * chart_height
            x = center + offset - (bar_width / 2)
            y = top + chart_height - height_value
            bars.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
                f'height="{height_value:.1f}" fill="{color}" rx="3">'
                f"<title>{escape(item['label'])}: {value} {key.replace('_', ' ')}</title>"
                "</rect>"
            )

    return _svg_chart(
        width,
        height,
        _grid_lines(max_value, left, top, chart_width, chart_height)
        + bars
        + _bar_x_labels(metrics, left, top, chart_width, chart_height)
        + _axis_line(left, top, chart_width, chart_height),
    )


def _run_metrics(run: history.RunSummary) -> dict[str, Any]:
    updates_by_server: dict[str, int] = {}
    reboot_required = 0
    docker_issues = 0

    for server in run.servers:
        if not isinstance(server, dict):
            continue
        server_id = str(server.get("server_id") or server.get("hostname") or "unknown")
        updates = server.get("updates") if isinstance(server.get("updates"), dict) else {}
        updates_by_server[server_id] = _as_int(updates.get("pending_total"))
        if updates.get("reboot_required"):
            reboot_required += 1

        docker = server.get("docker") if isinstance(server.get("docker"), dict) else {}
        unhealthy = docker.get("unhealthy") if isinstance(docker.get("unhealthy"), list) else []
        expected_stopped = (
            docker.get("expected_stopped")
            if isinstance(docker.get("expected_stopped"), list)
            else []
        )
        docker_issues += len(unhealthy) + len(expected_stopped)

    return {
        "label": run.generated_dt.astimezone().strftime("%m-%d %H:%M"),
        "critical": run.counts.get("critical", 0),
        "warning": run.counts.get("warning", 0),
        "info": run.counts.get("info", 0),
        "updates_by_server": updates_by_server,
        "reboot_required": reboot_required,
        "docker_issues": docker_issues,
    }


def _ordered_server_ids(runs: list[history.RunSummary]) -> list[str]:
    ordered: list[str] = []
    for run in reversed(runs):
        for server in run.servers:
            if not isinstance(server, dict):
                continue
            server_id = str(server.get("server_id") or server.get("hostname") or "unknown")
            if server_id not in ordered:
                ordered.append(server_id)
    return ordered


def _svg_chart(width: int, height: int, content: list[str]) -> str:
    return (
        '<div class="chart">'
        f'<svg role="img" viewBox="0 0 {width} {height}" '
        'xmlns="http://www.w3.org/2000/svg">'
        + "".join(content)
        + "</svg>"
        "</div>"
    )


def _grid_lines(
    max_value: int, left: int, top: int, chart_width: int, chart_height: int
) -> list[str]:
    lines: list[str] = []
    for tick in _axis_ticks(max_value):
        y = _y_position(tick, max_value, top, chart_height)
        lines.append(
            f'<line class="grid-line" x1="{left}" y1="{y:.1f}" '
            f'x2="{left + chart_width}" y2="{y:.1f}" />'
        )
        lines.append(
            f'<text class="axis-label" x="{left - 10}" y="{y + 4:.1f}" '
            f'text-anchor="end">{tick}</text>'
        )
    return lines


def _axis_line(left: int, top: int, chart_width: int, chart_height: int) -> list[str]:
    return [
        f'<line class="axis-line" x1="{left}" y1="{top + chart_height}" '
        f'x2="{left + chart_width}" y2="{top + chart_height}" />'
    ]


def _x_labels(
    metrics: list[dict[str, Any]],
    left: int,
    top: int,
    chart_width: int,
    chart_height: int,
) -> list[str]:
    labels: list[str] = []
    count = len(metrics)
    if count == 0:
        return labels
    label_every = 1 if count <= 7 else 2
    for index, item in enumerate(metrics):
        if index % label_every != 0 and index != count - 1:
            continue
        x = _x_position(index, count, left, chart_width)
        labels.append(
            f'<text class="axis-label" x="{x:.1f}" y="{top + chart_height + 22}" '
            f'text-anchor="middle">{escape(str(item["label"]))}</text>'
        )
    return labels


def _bar_x_labels(
    metrics: list[dict[str, Any]],
    left: int,
    top: int,
    chart_width: int,
    chart_height: int,
) -> list[str]:
    labels: list[str] = []
    count = len(metrics)
    if count == 0:
        return labels
    step = chart_width / count
    label_every = 1 if count <= 7 else 2
    for index, item in enumerate(metrics):
        if index % label_every != 0 and index != count - 1:
            continue
        x = left + (index * step) + (step / 2)
        labels.append(
            f'<text class="axis-label" x="{x:.1f}" y="{top + chart_height + 22}" '
            f'text-anchor="middle">{escape(str(item["label"]))}</text>'
        )
    return labels


def _chart_legend(items: list[tuple[str, str]]) -> str:
    entries = []
    for label, color in items:
        entries.append(
            '<span class="legend-item">'
            f'<span style="background:{escape(color)}"></span>'
            f"{escape(label)}"
            "</span>"
        )
    return f'<div class="legend">{"".join(entries)}</div>'


def _line_paths(points: list[tuple[float, float, int, str]]) -> list[str]:
    if not points:
        return []
    if len(points) == 1:
        x, y, _value, _label = points[0]
        return [f"M {x:.1f} {y:.1f}"]
    path = " ".join(
        f"{'M' if index == 0 else 'L'} {x:.1f} {y:.1f}"
        for index, (x, y, _value, _label) in enumerate(points)
    )
    return [path]


def _axis_ticks(max_value: int) -> list[int]:
    if max_value <= 4:
        return list(range(0, max_value + 1))
    midpoint = max(1, round(max_value / 2))
    return sorted({0, midpoint, max_value})


def _x_position(index: int, count: int, left: int, chart_width: int) -> float:
    if count <= 1:
        return left + (chart_width / 2)
    return left + (index * (chart_width / (count - 1)))


def _y_position(value: int, max_value: int, top: int, chart_height: int) -> float:
    return top + chart_height - ((value / max_value) * chart_height)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
    first = findings[0]
    return str(first.get("message") or first.get("title") or "Review finding")


def _display_time(run: history.RunSummary) -> str:
    return run.generated_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def _display_action_time(action: history.ActionSummary) -> str:
    return action.timestamp_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def _action_status_label(action: history.ActionSummary) -> str:
    if action.dry_run:
        return "dry-run"
    return action.status.lower().replace("_", "-")


def _format_arguments(arguments: dict[str, Any]) -> str:
    if not arguments:
        return "none"
    return ", ".join(
        f"{key}={arguments[key]}" for key in sorted(arguments) if arguments[key] is not None
    )


def _link(label: str, path: Path, output_dir: Path) -> str:
    href = os.path.relpath(path, output_dir).replace("\\", "/")
    return f'<a href="{escape(href)}">{escape(label)}</a>'


def _css() -> str:
    return """
:root {
  color-scheme: light;
  --bg: #f5f7f9;
  --panel: #ffffff;
  --text: #1f2933;
  --muted: #667085;
  --border: #d7dee8;
  --ok: #1f7a4d;
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
h1, h2, h3, p { margin-top: 0; }
h1 { font-size: 32px; margin-bottom: 4px; }
h2 { font-size: 20px; margin-bottom: 16px; }
h3 { font-size: 16px; margin-bottom: 10px; }
h4 {
  font-size: 14px;
  margin: 0 0 8px;
}
p, small, span, td, th, dd, dt { font-size: 14px; }
.topbar p, .metric small, .timeline-row span, .server-card p, .muted { color: var(--muted); }
.actions, .timeline-row nav {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
a {
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
}
a:hover { text-decoration: underline; }
.actions a, .timeline-row a {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 10px;
  background: var(--panel);
}
.tabbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 18px;
  border-bottom: 1px solid var(--border);
}
.tabbar a {
  border: 1px solid var(--border);
  border-bottom: 0;
  border-radius: 6px 6px 0 0;
  padding: 9px 12px;
  background: #eef4f6;
  color: var(--text);
}
.tabbar a:hover {
  background: var(--panel);
  text-decoration: none;
}
.view-section {
  scroll-margin-top: 16px;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.metric, .panel, .server-card, .empty {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.metric { padding: 14px; }
.metric span, .metric small { display: block; }
.metric strong {
  display: block;
  font-size: 24px;
  margin: 4px 0;
}
.panel, .empty {
  padding: 18px;
  margin-top: 18px;
}
.server-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}
.server-card {
  padding: 14px;
  border-top: 4px solid var(--ok);
}
.server-card.status-warning { border-top-color: var(--warning); }
.server-card.status-critical { border-top-color: var(--critical); }
.server-card.status-info { border-top-color: var(--info); }
.server-card h3 { margin-bottom: 4px; }
.server-facts {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 12px 0;
}
.server-facts div {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
}
.service-block {
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  padding: 12px 0;
  margin: 12px 0;
}
.service-list {
  display: grid;
  gap: 8px;
  list-style: none;
  margin: 0;
  padding: 0;
}
.service-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 8px;
}
.service-state {
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 700;
}
.service-ok { background: #e8f5ee; color: var(--ok); }
.service-bad { background: #fdecea; color: var(--critical); }
dt {
  color: var(--muted);
  margin-bottom: 2px;
}
dd {
  margin: 0;
  font-weight: 700;
}
.findings-table, .actions-table {
  width: 100%;
  border-collapse: collapse;
}
th, td {
  border-bottom: 1px solid var(--border);
  padding: 10px;
  text-align: left;
  vertical-align: top;
}
th {
  color: var(--muted);
  font-weight: 700;
}
.badge {
  display: inline-block;
  border-radius: 999px;
  padding: 3px 8px;
  font-weight: 700;
}
.badge-critical { background: #fdecea; color: var(--critical); }
.badge-warning { background: #fff4db; color: var(--warning); }
.badge-info { background: #eaf1ff; color: var(--info); }
.badge-action-completed { background: #e8f5ee; color: var(--ok); }
.badge-action-dry-run { background: #eaf1ff; color: var(--info); }
.badge-action-denied { background: #fff4db; color: var(--warning); }
.badge-action-failed { background: #fdecea; color: var(--critical); }
.badge-action-unknown { background: #eef2f7; color: var(--muted); }
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}
.section-heading h2 {
  margin-bottom: 0;
}
.section-heading span {
  color: var(--muted);
  white-space: nowrap;
}
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}
.chart-block {
  min-width: 0;
  border-top: 1px solid var(--border);
  padding-top: 14px;
}
.chart-block-wide {
  grid-column: 1 / -1;
}
.chart-block h3 {
  margin-bottom: 8px;
}
.chart {
  width: 100%;
  min-height: 210px;
}
.chart svg {
  display: block;
  width: 100%;
  height: auto;
}
.grid-line {
  stroke: #dfe6ef;
  stroke-width: 1;
}
.axis-line {
  stroke: #98a2b3;
  stroke-width: 1.2;
}
.axis-label {
  fill: var(--muted);
  font-size: 12px;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 8px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
}
.legend-item span {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}
.timeline {
  display: grid;
  gap: 10px;
  margin-bottom: 16px;
}
.timeline-row {
  display: grid;
  grid-template-columns: 1.4fr 1.7fr auto;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.timeline-row strong, .timeline-row span { display: block; }
.timeline-row p { margin: 0; color: var(--muted); }
code {
  font-family: Consolas, "Courier New", monospace;
  font-size: 0.95em;
}
@media (max-width: 820px) {
  .topbar, .timeline-row {
    display: block;
  }
  .actions, .timeline-row nav {
    margin-top: 10px;
  }
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .chart-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 560px) {
  .summary-grid, .server-facts {
    grid-template-columns: 1fr;
  }
  .section-heading {
    display: block;
  }
  .service-row {
    grid-template-columns: 1fr;
    align-items: start;
  }
  th, td {
    padding: 8px 6px;
  }
}
""".strip()
