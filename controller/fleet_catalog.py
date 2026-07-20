"""Fleet capability catalog generation."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from html import escape
from pathlib import Path
from typing import Any

from . import config, history
from .docker_inventory import (
    inventory_collected,
    load_container_classifications,
    normalize_docker_inventory,
    port_labels,
)
from .html_report_writer import ROLE_LABELS


def write_fleet_catalog(
    run: history.RunSummary,
    output_dir: Path | None = None,
    knowledge_path: Path | None = None,
) -> tuple[Path, Path]:
    """Write tracked catalog JSON and generated HTML for one run."""

    actual_knowledge_path = knowledge_path or config.FLEET_CATALOG_PATH
    actual_output_dir = output_dir or config.GENERATED_REPORTS_DIR
    catalog = build_fleet_catalog(
        run,
        fallback_servers=_fallback_server_catalogs(run, actual_knowledge_path),
        include_all_fallback_servers=True,
    )
    actual_knowledge_path.parent.mkdir(parents=True, exist_ok=True)
    actual_output_dir.mkdir(parents=True, exist_ok=True)

    actual_knowledge_path.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    html_path = actual_output_dir / "fleet-catalog.html"
    html_path.write_text(
        render_fleet_catalog(catalog, actual_output_dir),
        encoding="utf-8",
    )
    return actual_knowledge_path, html_path


def build_fleet_catalog(
    run: history.RunSummary,
    fallback_servers: dict[str, dict[str, Any]] | None = None,
    include_all_fallback_servers: bool = False,
) -> dict[str, Any]:
    """Build a stable catalog from the latest fleet run."""

    servers = [_server_catalog(server, run.findings) for server in run.servers]
    seen_server_ids = {str(server.get("server_id") or "") for server in servers}
    fallback_by_id = fallback_servers or {}
    for server_id in _failed_server_ids(run):
        if not server_id or server_id in seen_server_ids:
            continue
        fallback = fallback_by_id.get(server_id)
        if fallback:
            servers.append(_stale_server_catalog(server_id, fallback, run.findings))
        else:
            servers.append(_failed_server_catalog(server_id, run.findings))
        seen_server_ids.add(server_id)
    if include_all_fallback_servers:
        for server_id, fallback in fallback_by_id.items():
            if not server_id or server_id in seen_server_ids:
                continue
            servers.append(
                _preserved_server_catalog(
                    server_id,
                    fallback,
                    "not_in_latest_run",
                    "Not collected in latest run",
                )
            )
            seen_server_ids.add(server_id)
    servers = sorted(servers, key=_server_sort_key)
    return {
        "schema_version": "1.0",
        "generated_at": run.generated_at,
        "source": {
            "run_id": run.run_id,
            "generated_at": run.generated_at,
            "fleet_path": _repo_path(run.fleet_path),
        },
        "fleet_summary": _fleet_summary(servers),
        "recommendations": _fleet_recommendations(servers),
        "servers": servers,
    }


def render_fleet_catalog(catalog: dict[str, Any], output_dir: Path | None = None) -> str:
    """Render fleet catalog HTML."""

    actual_output_dir = output_dir or config.GENERATED_REPORTS_DIR
    servers = catalog.get("servers") if isinstance(catalog.get("servers"), list) else []
    source = catalog.get("source") if isinstance(catalog.get("source"), dict) else {}
    body = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>HomeOps Fleet Catalog</title>",
        "<style>",
        _css(),
        "</style>",
        "</head>",
        "<body>",
        '<main class="shell">',
        '<header class="topbar">',
        "<div>",
        "<h1>HomeOps Fleet Catalog</h1>",
        f"<p>Generated {escape(str(catalog.get('generated_at', 'unknown')))}</p>",
        "</div>",
        '<nav class="actions">',
        '<a href="index.html">Dashboard</a>',
        _link("Fleet JSON", Path(str(source.get("fleet_path", ""))), actual_output_dir),
        "</nav>",
        "</header>",
        _summary_section(catalog),
        _recommendations_section(catalog),
        '<section class="server-grid" aria-label="Server catalog">',
    ]

    for server in servers:
        if isinstance(server, dict):
            body.append(_server_card(server))

    body.extend(["</section>", "</main>", "</body>", "</html>"])
    return "\n".join(body) + "\n"


def _server_catalog(
    server: dict[str, Any], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    server_id = str(server.get("server_id") or "unknown")
    role = str(server.get("role") or "unknown")
    resources = server.get("resources") if isinstance(server.get("resources"), dict) else {}
    updates = server.get("updates") if isinstance(server.get("updates"), dict) else {}
    docker = server.get("docker") if isinstance(server.get("docker"), dict) else {}
    os_info = server.get("os") if isinstance(server.get("os"), dict) else {}
    hardware = server.get("hardware") if isinstance(server.get("hardware"), dict) else {}
    disks = _disks(server.get("disk"))
    services = _services(server.get("services"))
    server_findings = [
        finding for finding in findings if str(finding.get("server_id")) == server_id
    ]
    classifications = load_container_classifications(
        config.CONTAINER_CLASSIFICATIONS_PATH,
        server_id,
    )
    catalog = {
        "server_id": server_id,
        "hostname": str(server.get("hostname") or "unknown"),
        "role": role,
        "role_label": ROLE_LABELS.get(role, role),
        "collected_at": str(server.get("collected_at") or ""),
        "os": {
            "name": str(os_info.get("name") or "unknown"),
            "version": str(os_info.get("version") or "unknown"),
            "kernel": str(os_info.get("kernel") or "unknown"),
        },
        "hardware": {
            "architecture": _clean_text(hardware.get("architecture"), "unknown"),
            "cpu_model": _clean_text(hardware.get("cpu_model"), "unknown"),
            "memory_total_mb": _as_int(hardware.get("memory_total_mb")),
            "virtualization": _clean_virtualization(hardware.get("virtualization")),
        },
        "resources": {
            "cpu_count": _as_int(resources.get("cpu_count")),
            "load_1m": _as_float(resources.get("load_1m")),
            "memory_used_percent": _as_float(resources.get("memory_used_percent")),
            "swap_used_percent": _as_float(resources.get("swap_used_percent")),
            "uptime_days": round(_as_int(server.get("uptime_seconds")) / 86400, 1),
        },
        "storage": {
            "disks": disks,
            "root_free_gb": _root_disk_value(disks, "free_gb"),
            "root_used_percent": _root_disk_value(disks, "used_percent"),
            "total_reported_free_gb": sum(_as_int(disk.get("free_gb")) for disk in disks),
        },
        "services": services,
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
        "maintenance": {
            "pending_updates": _as_int(updates.get("pending_total")),
            "pending_security_updates": _as_int(updates.get("pending_security")),
            "reboot_required": bool(updates.get("reboot_required")),
        },
        "current_findings": [
            {
                "severity": str(finding.get("severity") or "info"),
                "code": str(finding.get("code") or "unknown"),
                "message": _clean_text(finding.get("message"), ""),
            }
            for finding in server_findings
        ],
    }
    catalog["capabilities"] = _capabilities(catalog)
    catalog["constraints"] = _constraints(catalog)
    catalog["placement_guidance"] = _placement_guidance(catalog)
    return catalog


def _fleet_summary(servers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "servers": len(servers),
        "cpu_threads": sum(server["resources"]["cpu_count"] for server in servers),
        "docker_hosts": sum(1 for server in servers if server["docker"]["installed"]),
        "running_containers": sum(
            server["docker"]["containers_running"] for server in servers
        ),
        "reboots_required": sum(
            1 for server in servers if server["maintenance"]["reboot_required"]
        ),
        "pending_updates": sum(
            server["maintenance"]["pending_updates"] for server in servers
        ),
        "collection_failed": sum(
            1 for server in servers if server.get("collection_status") == "failed_latest"
        ),
        "not_collected": sum(
            1
            for server in servers
            if server.get("collection_status") == "not_in_latest_run"
        ),
    }


def _fleet_recommendations(servers: list[dict[str, Any]]) -> list[str]:
    container_host = next(
        (server for server in servers if server.get("server_id") == "container-host"),
        None,
    )
    recommendations = [
        "Keep VPN access isolated on openvpn-server and avoid experimental workloads there.",
        "Keep camera recording isolated on ispy-server unless resource trends prove there is safe spare capacity.",
    ]
    if container_host and not container_host.get("constraints"):
        recommendations.append(
            "Use container-host as the Codex lab and default Docker experiment target."
        )
    else:
        recommendations.append(
            "Keep container-host maintenance current before increasing Docker workload."
        )
    if any(server["maintenance"]["reboot_required"] for server in servers):
        recommendations.append(
            "Clear reboot-required hosts before making placement changes."
        )
    if any(server["maintenance"]["pending_updates"] for server in servers):
        recommendations.append(
            "Apply pending package maintenance before using current capacity numbers for long-term planning."
        )
    return recommendations


def _capabilities(server: dict[str, Any]) -> list[str]:
    role = server["role"]
    cpu_count = server["resources"]["cpu_count"]
    docker = server["docker"]
    capabilities: list[str] = []
    if role == "openvpn_server":
        capabilities.extend(["VPN access gateway", "Low background workload"])
    elif role == "ispy_server":
        capabilities.extend(["Security camera service host", "AgentDVR workload"])
    elif role == "container_host":
        capabilities.extend(
            ["Codex lab host", "Docker application host", "Container consolidation target"]
        )
    if cpu_count >= 4:
        capabilities.append("Moderate CPU headroom")
    elif cpu_count:
        capabilities.append("Small CPU footprint")
    if docker["installed"]:
        capabilities.append(f"Docker installed with {docker['containers_running']} running containers")
    return capabilities


def _constraints(server: dict[str, Any]) -> list[str]:
    constraints: list[str] = []
    maintenance = server["maintenance"]
    docker = server["docker"]
    if maintenance["reboot_required"]:
        constraints.append("Reboot required")
    if maintenance["pending_updates"]:
        constraints.append(f"{maintenance['pending_updates']} package updates pending")
    if docker["unhealthy"]:
        names = ", ".join(item["name"] for item in docker["unhealthy"])
        constraints.append(f"Docker issue: {names}")
    failed_services = [
        service["name"]
        for service in server["services"]
        if service["state"] not in {"active", "unknown"}
    ]
    if failed_services:
        constraints.append(f"Service issue: {', '.join(failed_services)}")
    if server["role"] == "openvpn_server":
        constraints.append("VPN availability affects remote access")
    if server["role"] == "ispy_server":
        constraints.append("Camera recording interruption risk")
    return constraints


def _placement_guidance(server: dict[str, Any]) -> list[str]:
    role = server["role"]
    guidance: list[str] = []
    if role == "openvpn_server":
        guidance.append("Reserve for VPN and network access services.")
        guidance.append("Avoid CPU-heavy or experimental workloads.")
    elif role == "ispy_server":
        guidance.append("Prioritize AgentDVR and camera reliability.")
        guidance.append("Only add light support services after maintenance is current.")
    elif role == "container_host":
        guidance.append("Prefer this host for Codex lab experiments and Docker-backed applications.")
        if server["docker"]["unhealthy"]:
            guidance.append("Fix unhealthy containers before increasing workload.")
        elif server["maintenance"]["pending_updates"] or server["maintenance"]["reboot_required"]:
            guidance.append("Clear host maintenance before increasing workload.")
        else:
            guidance.append("Current host maintenance is clean; suitable for lab workloads.")
    return guidance


def _summary_section(catalog: dict[str, Any]) -> str:
    summary = catalog.get("fleet_summary") if isinstance(catalog.get("fleet_summary"), dict) else {}
    cards = [
        _metric("Servers", summary.get("servers", 0), "cataloged hosts"),
        _metric("CPU Threads", summary.get("cpu_threads", 0), "reported total"),
        _metric("Docker Hosts", summary.get("docker_hosts", 0), "container capable"),
        _metric("Containers", summary.get("running_containers", 0), "running now"),
        _metric("Pending Updates", summary.get("pending_updates", 0), "fleet total"),
    ]
    return '<section class="summary-grid">' + "".join(cards) + "</section>"


def _recommendations_section(catalog: dict[str, Any]) -> str:
    items = catalog.get("recommendations")
    if not isinstance(items, list):
        items = []
    return (
        '<section class="panel">'
        "<h2>Fleet Placement Guidance</h2>"
        "<ul>"
        + "".join(f"<li>{escape(str(item))}</li>" for item in items)
        + "</ul>"
        "</section>"
    )


def _server_card(server: dict[str, Any]) -> str:
    resources = server["resources"]
    hardware = server["hardware"]
    storage = server["storage"]
    maintenance = server["maintenance"]
    docker = server["docker"]
    collection_status = (
        "failed latest"
        if server.get("collection_status") == "failed_latest"
        else "current"
    )
    return (
        '<article class="server-card">'
        f"<h2>{escape(server['server_id'])}</h2>"
        f"<p>{escape(server['role_label'])} on <code>{escape(server['hostname'])}</code></p>"
        '<dl class="facts">'
        f"<div><dt>Collection</dt><dd>{escape(collection_status)}</dd></div>"
        f"<div><dt>OS</dt><dd>{escape(server['os']['name'])} {escape(server['os']['version'])}</dd></div>"
        f"<div><dt>Kernel</dt><dd>{escape(server['os']['kernel'])}</dd></div>"
        f"<div><dt>Architecture</dt><dd>{escape(hardware['architecture'])}</dd></div>"
        f"<div><dt>CPU Threads</dt><dd>{resources['cpu_count']}</dd></div>"
        f"<div><dt>Memory Total</dt><dd>{escape(_memory_label(hardware['memory_total_mb']))}</dd></div>"
        f"<div><dt>Load</dt><dd>{resources['load_1m']}</dd></div>"
        f"<div><dt>Memory Used</dt><dd>{resources['memory_used_percent']}%</dd></div>"
        f"<div><dt>Root Free</dt><dd>{storage['root_free_gb']} GB</dd></div>"
        f"<div><dt>Updates</dt><dd>{maintenance['pending_updates']}</dd></div>"
        f"<div><dt>Reboot</dt><dd>{'yes' if maintenance['reboot_required'] else 'no'}</dd></div>"
        f"<div><dt>Docker</dt><dd>{docker['containers_running']}/{docker['containers_total']} running</dd></div>"
        "</dl>"
        f"{_list_block('Capabilities', server['capabilities'])}"
        f"{_list_block('Constraints', server['constraints'])}"
        f"{_list_block('Placement', server['placement_guidance'])}"
        f"{_service_block(server['services'])}"
        f"{_container_inventory_block(docker)}"
        "</article>"
    )


def _metric(title: str, value: Any, detail: str) -> str:
    return (
        '<article class="metric">'
        f"<span>{escape(title)}</span>"
        f"<strong>{escape(str(value))}</strong>"
        f"<small>{escape(detail)}</small>"
        "</article>"
    )


def _list_block(title: str, items: list[str]) -> str:
    if not items:
        return ""
    return (
        f"<h3>{escape(title)}</h3>"
        "<ul>"
        + "".join(f"<li>{escape(str(item))}</li>" for item in items)
        + "</ul>"
    )


def _service_block(services: list[dict[str, Any]]) -> str:
    if not services:
        return ""
    rows = []
    for service in services:
        rows.append(
            "<tr>"
            f"<td><code>{escape(service['name'])}</code></td>"
            f"<td>{escape(service['state'])}</td>"
            f"<td>{'yes' if service['enabled'] else 'no'}</td>"
            "</tr>"
        )
    return (
        "<h3>Services</h3>"
        '<table class="service-table">'
        "<thead><tr><th>Name</th><th>State</th><th>Enabled</th></tr></thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _container_inventory_block(docker: dict[str, Any]) -> str:
    if not docker.get("installed"):
        return ""
    if not docker.get("inventory_collected"):
        return (
            '<h3>Container Inventory</h3>'
            '<p class="muted">Detailed inventory was not collected in this run.</p>'
        )
    containers = docker.get("containers")
    if not isinstance(containers, list) or not containers:
        return '<h3>Container Inventory</h3><p class="muted">No containers found.</p>'

    rows = []
    for container in containers:
        if not isinstance(container, dict):
            continue
        project = str(container.get("compose_project") or "standalone")
        service = str(container.get("compose_service") or "")
        if service:
            project = f"{project}/{service}"
        ports = port_labels(container)
        exposure = str(container.get("exposure") or "unknown")
        if ports:
            exposure = f"{exposure}: {', '.join(ports)}"
        state = str(container.get("state") or "unknown")
        health = str(container.get("health") or "none")
        if health != "none":
            state = f"{state} / {health}"
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(container.get('name') or 'unknown'))}</code></td>"
            f"<td><code>{escape(str(container.get('image') or 'unknown'))}</code></td>"
            f"<td>{escape(state)}</td>"
            f"<td>{escape(project)}</td>"
            f"<td>{escape(exposure)}</td>"
            f"<td><strong>{escape(str(container.get('classification') or 'unclassified'))}</strong><br>{escape(str(container.get('classification_rationale') or ''))}</td>"
            "</tr>"
        )
    return (
        "<h3>Container Inventory</h3>"
        '<div class="table-wrap"><table class="service-table">'
        "<thead><tr><th>Name</th><th>Image</th><th>State</th><th>Compose</th><th>Exposure</th><th>Review</th></tr></thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _disks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "mount": str(item.get("mount") or "unknown"),
            "used_percent": _as_int(item.get("used_percent")),
            "free_gb": _as_int(item.get("free_gb")),
            "size_gb": _as_int(item.get("size_gb")),
        }
        for item in value
        if isinstance(item, dict)
    ]


def _services(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "name": str(item.get("name") or "unknown"),
            "state": _clean_service_state(item.get("state")),
            "enabled": bool(item.get("enabled")),
        }
        for item in value
        if isinstance(item, dict)
    ]


def _root_disk_value(disks: list[dict[str, Any]], key: str) -> int:
    for disk in disks:
        if disk.get("mount") == "/":
            return _as_int(disk.get(key))
    return 0


def _memory_label(memory_total_mb: int) -> str:
    if memory_total_mb <= 0:
        return "unknown"
    if memory_total_mb >= 1024:
        return f"{round(memory_total_mb / 1024, 1)} GB"
    return f"{memory_total_mb} MB"


def _clean_text(value: Any, default: str) -> str:
    cleaned = " ".join(str(value or "").split())
    return cleaned or default


def _clean_virtualization(value: Any) -> str:
    cleaned = _clean_text(value, "unknown")
    if cleaned == "none none":
        return "none"
    return cleaned


def _clean_service_state(value: Any) -> str:
    cleaned = _clean_text(value, "unknown")
    if cleaned.endswith(" unknown"):
        return cleaned.split()[0]
    return cleaned


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


def _failed_server_ids(run: history.RunSummary) -> list[str]:
    server_ids: list[str] = []
    for error in run.collection_errors:
        server_id = str(error.get("server_id") or "")
        if server_id and server_id not in server_ids:
            server_ids.append(server_id)
    return server_ids


def _fallback_server_catalogs(
    run: history.RunSummary, knowledge_path: Path | None
) -> dict[str, dict[str, Any]]:
    fallback: dict[str, dict[str, Any]] = {}
    if knowledge_path:
        fallback.update(_catalog_servers_from_path(knowledge_path))

    runs_dir = run.fleet_path.parent.parent
    for previous_run in history.discover_run_summaries(runs_dir):
        if previous_run.run_id == run.run_id:
            continue
        for server in previous_run.servers:
            server_id = str(server.get("server_id") or "")
            if server_id and server_id not in fallback:
                fallback[server_id] = _server_catalog(server, previous_run.findings)
    return fallback


def _catalog_servers_from_path(path: Path) -> dict[str, dict[str, Any]]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(catalog, dict) or not isinstance(catalog.get("servers"), list):
        return {}

    servers: dict[str, dict[str, Any]] = {}
    for server in catalog["servers"]:
        if not isinstance(server, dict):
            continue
        server_id = str(server.get("server_id") or "")
        if server_id:
            servers[server_id] = server
    return servers


def _stale_server_catalog(
    server_id: str, fallback: dict[str, Any], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    catalog = _preserved_server_catalog(
        server_id,
        fallback,
        "failed_latest",
        "Latest collection failed",
    )
    catalog["current_findings"] = _finding_summaries(server_id, findings)
    return catalog


def _preserved_server_catalog(
    server_id: str,
    fallback: dict[str, Any],
    collection_status: str,
    constraint: str,
) -> dict[str, Any]:
    catalog = deepcopy(fallback)
    catalog["server_id"] = server_id
    catalog["collection_status"] = collection_status
    catalog["last_successful_collected_at"] = str(catalog.get("collected_at") or "")
    catalog["current_findings"] = []
    constraints = [str(item) for item in catalog.get("constraints", []) if str(item)]
    if constraint not in constraints:
        constraints.insert(0, constraint)
    catalog["constraints"] = constraints
    return catalog


def _failed_server_catalog(
    server_id: str, findings: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "server_id": server_id,
        "hostname": "unknown",
        "role": "unknown",
        "role_label": "unknown",
        "collected_at": "",
        "collection_status": "failed_latest",
        "last_successful_collected_at": "",
        "os": {"name": "unknown", "version": "unknown", "kernel": "unknown"},
        "hardware": {
            "architecture": "unknown",
            "cpu_model": "unknown",
            "memory_total_mb": 0,
            "virtualization": "unknown",
        },
        "resources": {
            "cpu_count": 0,
            "load_1m": 0.0,
            "memory_used_percent": 0.0,
            "swap_used_percent": 0.0,
            "uptime_days": 0,
        },
        "storage": {
            "disks": [],
            "root_free_gb": 0,
            "root_used_percent": 0,
            "total_reported_free_gb": 0,
        },
        "services": [],
        "docker": {
            "installed": False,
            "containers_total": 0,
            "containers_running": 0,
            "inventory_collected": False,
            "containers": [],
            "unhealthy": [],
        },
        "maintenance": {
            "pending_updates": 0,
            "pending_security_updates": 0,
            "reboot_required": False,
        },
        "current_findings": _finding_summaries(server_id, findings),
        "capabilities": [],
        "constraints": ["Latest collection failed"],
        "placement_guidance": [],
    }


def _finding_summaries(
    server_id: str, findings: list[dict[str, Any]]
) -> list[dict[str, str]]:
    return [
        {
            "severity": str(finding.get("severity") or "info"),
            "code": str(finding.get("code") or "unknown"),
            "message": _clean_text(finding.get("message"), ""),
        }
        for finding in findings
        if str(finding.get("server_id") or "") == server_id
    ]


def _server_sort_key(server: dict[str, Any]) -> tuple[int, str]:
    role_order = {"openvpn_server": 0, "ispy_server": 1, "container_host": 2}
    role = str(server.get("role") or "")
    server_id = str(server.get("server_id") or "")
    return (role_order.get(role, 99), server_id)


def _link(label: str, path: Path, output_dir: Path) -> str:
    if not str(path):
        return ""
    href = os.path.relpath(path, output_dir).replace("\\", "/")
    return f'<a href="{escape(href)}">{escape(label)}</a>'


def _repo_path(path: Path) -> str:
    try:
        return os.path.relpath(path, config.BASE_DIR).replace("\\", "/")
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
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 22px;
}
h1, h2, h3, p { margin-top: 0; }
h1 { font-size: 32px; margin-bottom: 4px; }
h2 { font-size: 20px; margin-bottom: 12px; }
h3 { font-size: 15px; margin: 16px 0 8px; }
p, small, span, td, th, li, dd, dt { font-size: 14px; }
.topbar p, .metric small, .server-card p, .muted { color: var(--muted); }
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
.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.metric, .panel, .server-card {
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
.panel {
  padding: 18px;
  margin-bottom: 18px;
}
.server-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}
.server-card {
  padding: 16px;
  border-top: 4px solid var(--accent);
}
.facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 14px 0;
}
.facts div {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
}
dt { color: var(--muted); margin-bottom: 2px; }
dd { margin: 0; font-weight: 700; overflow-wrap: anywhere; }
ul { padding-left: 20px; margin-bottom: 0; }
.service-table {
  width: 100%;
  border-collapse: collapse;
}
.table-wrap { overflow-x: auto; }
th, td {
  border-bottom: 1px solid var(--border);
  padding: 8px;
  text-align: left;
}
code {
  font-family: Consolas, "Courier New", monospace;
  font-size: 0.95em;
}
@media (max-width: 820px) {
  .topbar { display: block; }
  .actions { margin-top: 10px; }
  .summary-grid, .facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .summary-grid, .facts { grid-template-columns: 1fr; }
}
"""
