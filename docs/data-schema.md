# Data Schema

The first schema should be compact and stable enough for reports, local rules, and Codex analysis.

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
        "name": "homepage",
        "status": "unhealthy"
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
      "message": "Container homepage is unhealthy"
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
