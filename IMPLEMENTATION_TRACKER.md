# Implementation Tracker

This tracker records the planned implementation state for HomeOps Agent.

## Current Status

Project stage: read-only collection code is implemented and ready for server preparation.

Live status:

- Fixture-based reports work.
- Inventory loading works.
- SSH command dry-run works.
- Collector code writes raw results and `fleet-health.json`.
- Controller validates collected server health shapes before normalization.
- Inventory and SSH command building reject unapproved remote health commands.
- Local rule thresholds are loaded from `config/policy.yaml`.
- No real server collection has been run yet.

Current operating model:

- Controller is deterministic Python tooling.
- Codex in VS Code is the analyst.
- Servers expose scripts, not agents.
- No OpenAI API integration belongs in v1 controller code.
- All executable server-side changes must map to predefined action IDs.

## MVP Checklist

- [x] Create Python package skeleton under `controller/`.
- [x] Add CLI entrypoint at `controller/main.py`.
- [x] Add `config/servers.example.yaml`.
- [x] Add fixture data for one fake fleet run.
- [x] Generate a Markdown report from fixture data.
- [x] Add SSH inventory loading.
- [x] Add SSH collection wrapper with timeouts.
- [x] Add `server-scripts/common/health_summary.sh`.
- [x] Save raw run artifacts under `history/runs/<timestamp>/`.
- [x] Normalize server outputs into `fleet-health.json`.
- [x] Add local rules for disk, updates, services, Docker, and SSH login summaries.
- [x] Write generated report to `reports/generated/`.
- [x] Add action registry skeleton.
- [x] Add `actions list` command.
- [x] Keep mutating actions disabled until read-only collection is reliable.
- [x] Add initial unit tests for rules and report rendering.

## Initial Controller Modules

| Module | Purpose | Status |
|---|---|---|
| `controller/main.py` | CLI entrypoint | Implemented |
| `controller/config.py` | paths and settings | Implemented |
| `controller/inventory.py` | server inventory loading | Implemented |
| `controller/ssh_client.py` | SSH command execution | Implemented |
| `controller/collector.py` | orchestration of server collection | Implemented |
| `controller/normalizer.py` | common fleet model | Implemented |
| `controller/rules.py` | local issue detection | Implemented |
| `controller/policy.py` | policy loading and thresholds | Implemented |
| `controller/report_writer.py` | Markdown report generation | Implemented |
| `controller/action_registry.py` | allowed action definitions | Implemented |
| `controller/approvals.py` | approval checks and prompts | Planned |
| `controller/schemas.py` | schema loading and validation helpers | Implemented |

## First Server Scripts

| Script | Purpose | Risk | Status |
|---|---|---|---|
| `server-scripts/common/health_summary.sh` | combined read-only host summary | read_only | Implemented |
| `server-scripts/common/disk_check.sh` | mount usage summary | read_only | Planned |
| `server-scripts/common/update_check.sh` | apt update and reboot-required summary | read_only | Planned |
| `server-scripts/common/service_check.sh` | approved service status summary | read_only | Planned |
| `server-scripts/common/security_summary.sh` | SSH login and auth summary | read_only | Planned |
| `server-scripts/docker/docker_summary.sh` | Docker status and unhealthy containers | read_only | Planned |
| `server-scripts/openvpn/openvpn_status.sh` | OpenVPN service and client summary | read_only | Planned |
| `server-scripts/ispy/ispy_status.sh` | iSpy service and recording disk summary | read_only | Planned |

## Local Rule Backlog

- [x] `disk_usage_high`: any mount at or above 80%.
- [x] `disk_usage_critical`: any mount at or above 95%.
- [x] `service_failed`: approved service is not active.
- [x] `security_updates_pending`: one or more security updates pending.
- [x] `reboot_required`: server reports reboot required.
- [x] `docker_unhealthy_container`: Docker reports unhealthy containers.
- [x] `docker_container_stopped`: expected container is stopped.
- [x] `ssh_failed_login_spike`: failed SSH logins exceed policy threshold.
- [x] `collection_failed`: server collection fails or returns invalid JSON.

## Action Registry Backlog

Read-only action IDs are registered. Execution is still pending.

- [x] `collect_health`
- [x] `collect_disk`
- [x] `collect_updates`
- [x] `collect_services`
- [x] `collect_docker`
- [x] `collect_openvpn`
- [x] `collect_ispy`

Approval-required action IDs are registered but not executable.

- [x] `restart_service`
- [x] `restart_docker_container`
- [x] `apply_security_updates`
- [x] `reboot_server`

Forbidden actions:

- recursive deletion
- firewall changes
- arbitrary shell execution
- automatic port exposure
- SSH/OpenVPN/Docker/system config edits

## Next Implementation Step

Prepare for the first real read-only collection.

Recommended first task:

```text
Create config/servers.yaml from the example, install health_summary.sh on each server, run collect --dry-run, then run the first read-only collect.
```

Connection readiness:

- [x] Harden controller trust boundary before live SSH collection.
- [ ] Create local `config/servers.yaml`.
- [ ] Install `health_summary.sh` on `openvpn-server`.
- [ ] Install `health_summary.sh` on `ispy-server`.
- [ ] Install `health_summary.sh` on `container-host`.
- [ ] Validate script JSON output locally on each server.
- [ ] Confirm SSH key authentication from controller to each server.
- [ ] Run `python -m controller.main collect --dry-run`.
- [ ] Run first real `python -m controller.main collect`.
