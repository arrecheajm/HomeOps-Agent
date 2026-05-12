# Data Schema

The first schema should be compact and stable enough for reports, local rules, and Codex analysis.

## Inventory JSON

Each configured server includes connection details plus the authority model:

```json
{
  "server_id": "ispy-server",
  "role": "ispy_server",
  "host": "ispy-server.local",
  "user": "homeops",
  "access_profile": "experimental",
  "rebuildable": true,
  "remote_health_command": "/opt/homeops-agent/server-scripts/common/health_summary.sh"
}
```

Allowed `access_profile` values:

- `guarded`: predefined actions only; cannot be rebuildable.
- `experimental`: repairable project server; future logged admin workflows.
- `lab`: disposable playground server; future broad logged admin workflows.

## Per-Server Health JSON

Each server collection script should output a single JSON object:

```json
{
  "schema_version": "1.0",
  "server_id": "container-host",
  "role": "container_host",
  "collected_at": "2026-05-04T18:30:00Z",
  "hostname": "container-host",
  "os": {
    "name": "Ubuntu",
    "version": "24.04",
    "kernel": "6.8.0"
  },
  "hardware": {
    "architecture": "x86_64",
    "cpu_model": "Intel(R) Core(TM) ...",
    "memory_total_mb": 8192,
    "virtualization": "none"
  },
  "uptime_seconds": 345992,
  "resources": {
    "load_1m": 0.42,
    "cpu_count": 4,
    "memory_used_percent": 61.2,
    "swap_used_percent": 4.5
  },
  "disk": [
    {
      "mount": "/",
      "used_percent": 72,
      "free_gb": 85.4
    }
  ],
  "updates": {
    "pending_total": 14,
    "pending_security": 2,
    "reboot_required": false
  },
  "services": [
    {
      "name": "ssh",
      "state": "active",
      "enabled": true
    },
    {
      "name": "docker",
      "state": "active",
      "enabled": true
    }
  ],
  "docker": {
    "installed": true,
    "containers_total": 12,
    "containers_running": 11,
    "unhealthy": [
      {
        "name": "watchtower",
        "status": "Restarting (1) 44 seconds ago"
      }
    ]
  },
  "security": {
    "failed_ssh_logins_24h": 3,
    "successful_ssh_logins_24h": 2,
    "last_login_summary": [
      "admin from 192.168.1.20"
    ]
  },
  "issues": [
    {
      "severity": "warning",
      "code": "docker_unhealthy_container",
      "message": "Container watchtower is reporting Restarting (1) 44 seconds ago."
    }
  ]
}
```

## Fleet Health JSON

The controller should combine server results into one fleet object:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-05-04T18:31:00Z",
  "servers_checked": 3,
  "servers_failed": 0,
  "servers": [],
  "findings": [],
  "collection_errors": []
}
```

During normalization, inventory values are authoritative for `server_id` and `role`. Remote script values are useful diagnostics, but they must not replace inventory identity. When the remote script reports those fields, the controller may preserve them as `reported_server_id` and `reported_role` on the normalized server object.

Collected per-server JSON is accepted only when key sections have the expected shapes:

- `disk` and `services` must be lists of objects.
- `updates`, `docker`, and `security` must be objects.
- numeric counters and percentages must be numbers.
- boolean state fields such as `updates.reboot_required` and `docker.installed` must be booleans.

Invalid shapes are recorded as collection failures instead of being passed to local rules or report rendering.

## Fleet Catalog JSON

The repository keeps a tracked capability catalog at:

```text
knowledge/fleet-catalog.json
```

The catalog is generated from the latest fleet health JSON and includes:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-05-10T20:00:00Z",
  "source": {
    "run_id": "2026-05-10T19-49-53Z",
    "generated_at": "2026-05-10T19:49:53Z",
    "fleet_path": "history/runs/2026-05-10T19-49-53Z/fleet-health.json"
  },
  "fleet_summary": {
    "servers": 3,
    "cpu_threads": 10,
    "docker_hosts": 1,
    "running_containers": 9,
    "reboots_required": 2,
    "pending_updates": 124
  },
  "recommendations": [],
  "servers": []
}
```

Server catalog entries intentionally omit login history and secrets. They keep
role, hostname, OS, hardware, service, maintenance, storage, Docker, capability,
constraint, and placement guidance fields. Older collection runs may not include
hardware details; the catalog treats missing hardware fields as `unknown`.

## Finding Object

Local rules should produce finding objects:

```json
{
  "server_id": "ispy-server",
  "severity": "warning",
  "code": "disk_usage_high",
  "title": "Disk usage is high",
  "message": "Mount / is 84% full.",
  "evidence": {
    "mount": "/",
    "used_percent": 84
  },
  "recommended_action_ids": []
}
```

## Severity Levels

- `critical`: immediate attention likely needed
- `warning`: should be addressed soon
- `info`: useful operational note

## Schema Guidelines

- Keep raw logs out of normal reports.
- Use counts, states, timestamps, and short summaries.
- Include enough evidence for a junior-to-mid level engineer to understand the issue.
- Prefer `null` or omitted role-specific sections when a check is not applicable.
- Preserve raw collection output in history for debugging.
- Keep local rule thresholds in `config/policy.yaml` so report behavior can be tuned without changing controller code.
