# Implementation Tracker

This tracker records the implementation state for HomeOps Agent.

## Current Status

Project stage: collection, reporting, fleet catalog generation, access profiles,
and narrow approval-gated actions are live for all configured servers.

Live status:

- Fixture-based reports work.
- Inventory loading works.
- SSH command dry-run works.
- SSH inventory supports optional identity files for dedicated controller keys.
- SSH collection passes inventory `server_id` and `role` into the health script.
- Collector code writes raw results and `fleet-health.json`.
- Controller validates collected server health shapes before normalization.
- Inventory and SSH command building reject unapproved remote health commands.
- Local rule thresholds are loaded from `config/policy.yaml`.
- First real collection succeeded for `openvpn-server`, `ispy-server`, and
  `container-host`.
- Role-aware collection was verified on May 10, 2026.
- `container-host` is online at `192.168.86.58`, reachable as
  `containerserver@192.168.86.58`, and included in normal collection.
- HTML dashboard generation is implemented for latest status, historical charts,
  agent/action history, and grouped run history.
- Fleet capability catalog generation is implemented for tracked repo knowledge
  and separate HTML reporting.
- Before-state snapshot generation is implemented for rebuildable servers.
- Rebuild plan generation is implemented for rebuildable servers from
  before-state snapshots.
- `deploy_health_script`, `restart_docker_container`, and `restart_service`
  support dry-run, exact approval, execution, and action history.
- `run_admin_command` supports dry-run, exact approval, execution, and action
  history for `experimental` and `lab` servers only.
- The current `health_summary.sh` script was deployed through the approval-gated
  `deploy_health_script` action to all three configured servers on May 10, 2026.
- The latest tracked fleet catalog is based on run
  `2026-05-12T17-16-00Z`, after the latest fleet review and action attempts.
- The `run fleet review` operator workflow is documented for Codex: collect
  live health, refresh dashboard and catalog, check the latest run explicitly,
  summarize findings, and recommend next steps without executing
  approval-required actions.
- Inventory now distinguishes `guarded`, `experimental`, and `lab` access
  profiles, with rebuildability tracked separately.
- The project operating model is a personal homelab agent controller:
  `openvpn-server` stays guarded for access, `ispy-server` is the intermediate
  experimental/rebuildable box, and `container-host` is the Codex lab with full
  logged sudo authority.

Current operating model:

- Controller is deterministic Python tooling.
- Codex in VS Code is the analyst.
- Servers expose scripts, not agents.
- No OpenAI API integration belongs in v1 controller code.
- All executable server-side changes must map to predefined action IDs.

## Baseline Checklist

- [x] Create Python package skeleton under `controller/`.
- [x] Add CLI entrypoint at `controller/main.py`.
- [x] Add `config/servers.example.yaml`.
- [x] Add fixture data for one fake fleet run.
- [x] Generate an HTML report/dashboard from fixture data.
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
- [x] Gate mutating actions behind registry definitions, policy checks, exact
  approval, and action history.
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
| `controller/html_report_writer.py` | HTML dashboard generation | Implemented |
| `controller/fleet_catalog.py` | fleet capability catalog generation | Implemented |
| `controller/history.py` | run history loading and grouping | Implemented |
| `controller/action_registry.py` | allowed action definitions | Implemented |
| `controller/approvals.py` | approval checks and prompts | Implemented |
| `controller/action_runner.py` | action execution and history | Implemented |
| `controller/schemas.py` | schema loading and validation helpers | Implemented |

## First Server Scripts

| Script | Purpose | Risk | Status |
|---|---|---|---|
| `server-scripts/common/health_summary.sh` | combined read-only host summary with role-specific service selection | read_only | Implemented |
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

Collection action IDs are registered for policy and reporting. Standalone
execution for these collection IDs is still pending; normal health collection
currently runs through `python -m controller.main collect`.

- [x] `collect_health`
- [x] `collect_disk`
- [x] `collect_updates`
- [x] `collect_services`
- [x] `collect_docker`
- [x] `collect_openvpn`
- [x] `collect_ispy`

Approval-required action IDs are registered. `restart_docker_container`,
`restart_service`, `deploy_health_script`, `apply_security_updates`, and
`reboot_server` are executable after exact approval. `run_admin_command` is
also executable after exact approval on `experimental` and `lab` profiles.

- [x] `deploy_health_script`
- [x] `restart_service`
- [x] `restart_docker_container`
- [x] `reboot_server`
- [x] `apply_security_updates`
- [x] `run_admin_command`

Currently blocked outside a future explicit rebuild workflow or policy change:

- recursive deletion
- firewall changes
- unlogged arbitrary shell execution
- automatic port exposure
- SSH/OpenVPN/Docker/system config edits

## Next Implementation Step

Operationally, follow `docs/active-operations-plan.md`: install the right
sudoers profile on each server, preserve VPN access on the guarded server, use
`ispy-server` for intermediate repair work, and use `container-host` as the
full-sudo Codex lab.

The next implementation item is an explicit rebuild execution design for
rebuildable servers. It should stay separate from `run_admin_command`.

For live rule checks, pass the latest run explicitly because `check` without
`--input` defaults to fixture data:

```powershell
python -m controller.main check --input history\runs\<latest-run>\fleet-health.json
```

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
- [x] Deploy the current `health_summary.sh` to all configured servers through
  `deploy_health_script`.

Reporting readiness:

- [x] Group run history by practical operating periods.
- [x] Generate HTML dashboard from structured run history.
- [x] Show action history in the HTML dashboard.
- [x] Show agent/action history metrics, outcome chart, and timeline in the HTML dashboard.
- [x] Show historical dashboard charts for findings, updates, reboots, and Docker issues.
- [x] Refresh HTML dashboard after collection.
- [x] Refresh HTML dashboard after action attempts.
- [x] Generate tracked fleet capability catalog JSON.
- [x] Generate separate fleet catalog HTML report.
- [x] Refresh the tracked fleet catalog after health script deployment.
- [x] Document the `run fleet review` Codex workflow.

Access profile readiness:

- [x] Add `access_profile` to inventory.
- [x] Add `rebuildable` to inventory.
- [x] Update example inventory with guarded, experimental, and lab profiles.
- [x] Add access profile documentation.
- [x] Add sudoers profile templates.
- [x] Add logged admin-command support for experimental/lab profiles.
- [x] Add before-state capture for rebuildable servers.
- [x] Add rebuild planning workflow for rebuildable servers.
- [ ] Design approval-gated rebuild execution workflow.
