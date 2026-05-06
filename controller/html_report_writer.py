"""HTML dashboard rendering for HomeOps run history."""

from __future__ import annotations

import os
from html import escape
from pathlib import Path
from typing import Any

from . import config, history, rules
from .report_writer import ROLE_LABELS


def write_dashboard(
    runs: list[history.RunSummary], output_dir: Path | None = None
) -> Path:
    """Render and write the HTML dashboard."""

    actual_output_dir = output_dir or config.GENERATED_REPORTS_DIR
    actual_output_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = actual_output_dir / "index.html"
    dashboard_path.write_text(
        render_dashboard(runs, actual_output_dir),
        encoding="utf-8",
    )
    return dashboard_path


def render_dashboard(
    runs: list[history.RunSummary], output_dir: Path | None = None
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

    body.extend(_summary_cards(latest))
    body.extend(_server_section(latest))
    body.extend(_findings_section(latest))
    body.extend(_timeline_section(sorted_runs, actual_output_dir))
    body.extend(["</main>", "</body>", "</html>"])
    return "\n".join(body) + "\n"


def _latest_link(run: history.RunSummary | None, output_dir: Path) -> str:
    if not run:
        return ""
    links = [_link("Fleet JSON", run.fleet_path, output_dir)]
    if run.report_path:
        links.insert(0, _link("Markdown Report", run.report_path, output_dir))
    return f'<nav class="actions">{"".join(links)}</nav>'


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


def _timeline_section(runs: list[history.RunSummary], output_dir: Path) -> list[str]:
    lines = ['<section class="panel">', "<h2>Run Timeline</h2>"]
    for label, grouped_runs in history.group_runs_by_period(runs):
        lines.extend([f"<h3>{escape(label)}</h3>", '<div class="timeline">'])
        for run in grouped_runs:
            links = [_link("JSON", run.fleet_path, output_dir)]
            if run.report_path:
                links.insert(0, _link("Markdown", run.report_path, output_dir))
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
p, small, span, td, th, dd, dt { font-size: 14px; }
.topbar p, .metric small, .timeline-row span, .server-card p { color: var(--muted); }
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
dt {
  color: var(--muted);
  margin-bottom: 2px;
}
dd {
  margin: 0;
  font-weight: 700;
}
.findings-table {
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
}
@media (max-width: 560px) {
  .summary-grid, .server-facts {
    grid-template-columns: 1fr;
  }
  th, td {
    padding: 8px 6px;
  }
}
""".strip()
