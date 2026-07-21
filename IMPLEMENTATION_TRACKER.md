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
- Focused `container-review` reporting is implemented for container-host
  diagnosis, recommended dry-run fixes, and verification commands.
- Focused `ispy-review` reporting is implemented for iSpy/AgentDVR reliability
  work, including service diagnosis, before-state context, recent action
  history, sanitized AgentDVR evidence, recording gaps, endpoint checks, and
  recommended next steps.
- Before-state snapshot generation is implemented for rebuildable servers.
- Rebuild plan generation is implemented for rebuildable servers from
  before-state snapshots.
- `inspect_docker_container`, `replace_watchtower_container`,
  `migrate_watchtower_container`, `deploy_health_script`,
  `retire_disposable_containers`, `preflight_monitoring_images`,
  `provision_monitoring_secret`, `deploy_monitoring_stack`,
  `rollback_monitoring_stack`,
  `deploy_sudoers_profile`, `restart_docker_container`, `restart_service`,
  `apply_package_updates`, `apply_security_updates`, and `reboot_server`
  support dry-run, exact approval, execution, and action history.
- `run_admin_command` supports dry-run, exact approval, execution, and action
  history for `experimental` and `lab` servers only.
- The current `health_summary.sh` script was deployed through the approval-gated
  `deploy_health_script` action to all three configured servers on May 10, 2026.
- The latest tracked fleet catalog is based on run
  `2026-07-21T12-13-24Z`; all three servers collected successfully and
  `container-host` has 6 of 6 containers running. Current maintenance findings
  are 5 security updates on `ispy-server` plus non-security package updates on
  `openvpn-server` and `container-host`; no server requires a reboot.
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
- The accepted `container-host` application direction is the LAN-only House OS
  in `docs/container-host-house-os-plan.md`: smart-home control, Paperless-ngx
  and Mealie, Forgejo, a 1 TB USB data drive, and HomeOps-managed lifecycle and
  recovery workflows.
- Sanitized Docker inventory is implemented locally in `health_summary.sh`,
  validated as nested health data, and surfaced in the dashboard, fleet
  catalog, and container review without logs, environment values, or arbitrary
  labels. The updated script was deployed through the approval-gated action on
  2026-07-20 and a targeted run successfully collected all 9 containers.
- Local container disposition recommendations are tracked in
  `config/container-classifications.yaml` and rendered with rationale in the
  fleet catalog and container review.
- A sanitized read-only storage/database probe confirmed that the legacy
  `/mnt/storage*` paths are nearly empty root-filesystem directories, not
  external mounts. Point-in-time evidence is tracked in
  `config/container-review-evidence.yaml` and rendered in the container review.
- Legacy database review found about 210 MiB in the MySQL 5.7 volume and about
  46 MiB in the PostgreSQL 15 volume. PostgreSQL contains `nonprofit_app`; no
  application container peers were found for either database.
- Desired workload configuration is implemented in `config/workloads.yaml` and
  normalized by `controller/workloads.py`. The focused container review renders
  six ordered LAN-only workloads and keeps deployment gated until prerequisites
  and version-pinned Compose definitions exist.
- The operator confirmed `filebrowser` was empty and the MySQL/PostgreSQL
  volumes contained disposable development-test data. The approved
  `retire_disposable_containers` action removed those three containers and their
  fixed data-volume bundle on 2026-07-20; targeted and full-fleet collections
  verified 6 of 6 remaining containers with no container-host findings.
- The monitoring migration strategy is a clean rebuild. The current basic
  Grafana state and Prometheus history are disposable; the documented plan
  keeps old volumes only through rollback acceptance and records every proposed
  upgrade and rationale in `docs/monitoring-stack-upgrade-review.md`.
- The live monitoring preflight is complete and the first
  `stacks/monitoring/` replacement bundle is implemented. Docker Compose
  renders it successfully; 118 tests cover version pinning, LAN exposure,
  retained scrape targets, dashboard structure, and four committed
  Linux/amd64 registry digests. Exact-image health checks have passed; cutover
  remains gated on its untracked secret and separate approval.
- The approved `preflight_monitoring_images` execution passed on 2026-07-21;
  targeted inventory afterward confirmed the same 6 of 6 original containers
  running. The fixed `deploy_monitoring_stack` and `rollback_monitoring_stack`
  lifecycle is implemented and dry-run verified but has not been executed.
- Read-only inspection identified the five `ispy-server` security entries as
  two architectures each of `libde265-0` and `libsqlite3-0`, plus `wget`.
  `snapd` is the one non-security entry; AgentDVR is not itself pending.
- `provision_monitoring_secret` is implemented and dry-run verified. It creates
  or validates the fixed server-side secret without logging its value and
  copies it to the ignored local recovery path. Its approved execution passed
  on 2026-07-21, and the ignored local copy was verified without displaying it.

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
| `controller/ispy_review.py` | focused iSpy/AgentDVR reliability report generation | Implemented |
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
`restart_service`, `deploy_health_script`, `deploy_sudoers_profile`,
`inspect_docker_container`, `replace_watchtower_container`,
`migrate_watchtower_container`, `retire_disposable_containers`,
`preflight_monitoring_images`, `provision_monitoring_secret`, `deploy_monitoring_stack`,
`rollback_monitoring_stack`,
`apply_package_updates`,
`apply_security_updates`, and `reboot_server` are executable after exact
approval. `run_admin_command` is also executable after exact approval on
`experimental` and `lab` profiles.

- [x] `deploy_health_script`
- [x] `deploy_sudoers_profile`
- [x] `inspect_docker_container`
- [x] `replace_watchtower_container`
- [x] `migrate_watchtower_container`
- [x] `retire_disposable_containers`
- [x] `preflight_monitoring_images`
- [x] `provision_monitoring_secret`
- [x] `deploy_monitoring_stack`
- [x] `rollback_monitoring_stack`
- [x] `restart_service`
- [x] `restart_docker_container`
- [x] `reboot_server`
- [x] `apply_package_updates`
- [x] `apply_security_updates`
- [x] `run_admin_command`

Currently blocked outside a future explicit rebuild workflow or policy change:

- recursive deletion
- firewall changes
- unlogged arbitrary shell execution
- automatic port exposure
- SSH/OpenVPN/Docker/system config edits

## Next Implementation Step

The next operational item is separately approving
`deploy_monitoring_stack`. After cutover, verify the
Grafana login, Prometheus targets, dashboard, private port boundary, reboot
persistence, and rollback before old monitoring state is removed. The USB
mount/sentinel preflight follows. Use
`docs/container-host-house-os-plan.md` as the acceptance and delivery-order
source.

Explicit rebuild execution design remains a separate later item and must stay
separate from `run_admin_command`.

For day-to-day Codex resume state, use `ACTIVE_WORK.md` and the generated
`reports/generated/codex-brief.md`. Do not use this tracker as the first file
for every session.

Operationally, preserve VPN access on the guarded server, use `ispy-server` for
intermediate repair work, and use `container-host` as the full-sudo Codex lab
now that its sudoers profile, Watchtower migration, package updates, and reboot
verification are complete.

For live rule checks, pass the latest run explicitly because `check` without
`--input` defaults to fixture data:

```powershell
python -m controller.main check --input history\runs\<latest-run>\fleet-health.json
```

Current daily handoff is tracked in:

```text
ACTIVE_WORK.md
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
- [x] Generate container host review reports with recommended dry-run fixes.
- [x] Generate iSpy/AgentDVR review reports with service, recording, and
  sanitized endpoint evidence.
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
