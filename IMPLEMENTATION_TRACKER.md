# Implementation Tracker

This tracker records the planned implementation state for HomeOps Agent.

## Current Status

Project stage: planning complete, implementation ready to start.

Current operating model:

- Controller is deterministic Python tooling.
- Codex in VS Code is the analyst.
- Servers expose scripts, not agents.
- No OpenAI API integration belongs in v1 controller code.
- All executable server-side changes must map to predefined action IDs.

## MVP Checklist

- [ ] Create Python package skeleton under `controller/`.
- [ ] Add CLI entrypoint at `controller/main.py`.
- [ ] Add `config/servers.example.yaml`.
- [ ] Add fixture data for one fake fleet run.
- [ ] Generate a Markdown report from fixture data.
- [ ] Add SSH inventory loading.
- [ ] Add SSH collection wrapper with timeouts.
- [ ] Add `server-scripts/common/health_summary.sh`.
- [ ] Save raw run artifacts under `history/runs/<timestamp>/`.
- [ ] Normalize server outputs into `fleet-health.json`.
- [ ] Add local rules for disk, updates, services, Docker, and SSH login summaries.
- [ ] Write generated report to `reports/generated/`.
- [ ] Add action registry skeleton.
- [ ] Add `actions list` command.
- [ ] Keep mutating actions disabled until read-only collection is reliable.

## Initial Controller Modules

| Module | Purpose | Status |
|---|---|---|
| `controller/main.py` | CLI entrypoint | Planned |
| `controller/config.py` | paths and settings | Planned |
| `controller/inventory.py` | server inventory loading | Planned |
| `controller/ssh_client.py` | SSH command execution | Planned |
| `controller/collector.py` | orchestration of server collection | Planned |
| `controller/normalizer.py` | common fleet model | Planned |
| `controller/rules.py` | local issue detection | Planned |
| `controller/report_writer.py` | Markdown report generation | Planned |
| `controller/action_registry.py` | allowed action definitions | Planned |
| `controller/approvals.py` | approval checks and prompts | Planned |
| `controller/schemas.py` | schema loading and validation helpers | Planned |

## First Server Scripts

| Script | Purpose | Risk | Status |
|---|---|---|---|
| `server-scripts/common/health_summary.sh` | combined read-only host summary | read_only | Planned |
| `server-scripts/common/disk_check.sh` | mount usage summary | read_only | Planned |
| `server-scripts/common/update_check.sh` | apt update and reboot-required summary | read_only | Planned |
| `server-scripts/common/service_check.sh` | approved service status summary | read_only | Planned |
| `server-scripts/common/security_summary.sh` | SSH login and auth summary | read_only | Planned |
| `server-scripts/docker/docker_summary.sh` | Docker status and unhealthy containers | read_only | Planned |
| `server-scripts/openvpn/openvpn_status.sh` | OpenVPN service and client summary | read_only | Planned |
| `server-scripts/ispy/ispy_status.sh` | iSpy service and recording disk summary | read_only | Planned |

## Local Rule Backlog

- [ ] `disk_usage_warning`: any mount at or above 80%.
- [ ] `disk_usage_critical`: any mount at or above 95%.
- [ ] `service_failed`: approved service is not active.
- [ ] `security_updates_pending`: one or more security updates pending.
- [ ] `reboot_required`: server reports reboot required.
- [ ] `docker_unhealthy_container`: Docker reports unhealthy containers.
- [ ] `docker_container_stopped`: expected container is stopped.
- [ ] `ssh_failed_login_spike`: failed SSH logins exceed policy threshold.
- [ ] `collection_failed`: server collection fails or returns invalid JSON.

## Action Registry Backlog

Read-only actions first:

- [ ] `collect_health`
- [ ] `collect_disk`
- [ ] `collect_updates`
- [ ] `collect_services`
- [ ] `collect_docker`
- [ ] `collect_openvpn`
- [ ] `collect_ispy`

Approval-required actions later:

- [ ] `restart_service`
- [ ] `restart_docker_container`
- [ ] `apply_security_updates`
- [ ] `reboot_server`

Forbidden actions:

- recursive deletion
- firewall changes
- arbitrary shell execution
- automatic port exposure
- SSH/OpenVPN/Docker/system config edits

## Next Implementation Step

Start with the controller skeleton and fixture-driven report generation before connecting to real servers.

Recommended first task:

```text
Create controller CLI, fixture fleet JSON, and Markdown report writer.
```
