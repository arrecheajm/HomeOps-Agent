# Implementation Tracker

This tracker records the implementation state for HomeOps Agent.

## Current Status

Project stage: read-only collection and reporting are live for all configured servers.

Live status:

- Fixture-based reports work.
- Inventory loading works.
- SSH command dry-run works.
- SSH inventory supports optional identity files for dedicated controller keys.
- Collector code writes raw results and `fleet-health.json`.
- Controller validates collected server health shapes before normalization.
- Inventory and SSH command building reject unapproved remote health commands.
- Local rule thresholds are loaded from `config/policy.yaml`.
- First real read-only collection succeeded for `openvpn-server`, `ispy-server`,
  and `container-host`.
- `container-host` is online at `192.168.86.58`, reachable as
  `containerserver@192.168.86.58`, and included in normal collection.
- HTML dashboard generation is implemented for grouped run history.

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
- [x] Add optional SSH identity file support.
- [x] Add `server-scripts/common/health_summary.sh`.
- [x] Save raw run artifacts under `history/runs/<timestamp>/`.
- [x] Normalize server outputs into `fleet-health.json`.
- [x] Add local rules for disk, updates, services, Docker, and SSH login summaries.
- [x] Write generated report to `reports/generated/`.
- [x] Write generated HTML dashboard to `reports/generated/index.html`.
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
| `controller/html_report_writer.py` | HTML dashboard generation | Implemented |
| `controller/history.py` | run history loading and grouping | Implemented |
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

Review the current fleet findings, especially the restarting `watchtower`
container on `container-host`, then decide whether to implement approval-gated
maintenance actions.

Current operations are tracked in:

```text
docs/active-operations-plan.md
```

Manual update/reboot workflow is tracked in:

```text
docs/manual-maintenance-runbook.md
```

Connection readiness:

- [x] Harden controller trust boundary before live SSH collection.
- [x] Create local `config/servers.yaml` for enabled servers.
- [x] Install `health_summary.sh` on `openvpn-server`.
- [x] Install `health_summary.sh` on `ispy-server`.
- [x] Install `health_summary.sh` on `container-host`.
- [x] Validate script JSON output locally on each configured server.
- [x] Confirm SSH key authentication from controller to each configured server.
- [x] Run `python -m controller.main collect --dry-run`.
- [x] Run first real `python -m controller.main collect` for all configured servers.

Reporting readiness:

- [x] Group run history by practical operating periods.
- [x] Generate HTML dashboard from structured run history.
- [x] Refresh HTML dashboard after collection.
