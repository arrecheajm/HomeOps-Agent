# Active Work

Purpose: this is the daily Codex handoff. Read this first before inspecting
broader docs, history, generated reports, or source files.

Last updated: 2026-07-22.

## Session Start

Use this prompt for normal project sessions:

```text
Quick resume. Read ACTIVE_WORK.md and reports/generated/codex-brief.md only,
then continue the next step. Keep output concise and do not run a full fleet
review unless I ask for it.
```

Refresh the generated brief when report pointers may be stale:

```powershell
python -m controller.main codex-brief
```

## Thinking Level Guidance

- Start at `medium` for daily quick resume, status-only work, doc cleanup, and
  narrow edits with clear acceptance criteria.
- Use `high` for normal implementation, test failures, CLI behavior changes,
  and cross-file code changes after the scope is known.
- Use `extra high` only for approval-gated server mutation design, rebuild
  execution design, security boundaries, architecture changes, or confusing
  failures where the cheaper pass did not explain the issue.

Default daily pattern: begin at `medium`, then raise to `high` only when the
next concrete implementation task needs it.

## Current Project Focus

Primary operating model: HomeOps Agent is a deterministic local controller.
Codex reads local evidence and recommends next steps. Managed servers run
approved scripts and predefined action IDs, not autonomous agents.

Current implementation focus:

- Plan and implement the LAN-only `container-host` House OS described in
  `docs/container-host-house-os-plan.md`.
- Keep `openvpn-server` guarded and avoid VPN-impacting work unless explicitly
  requested.
- Keep the currently healthy `ispy-server` camera workload isolated from the
  new household services.
- Extend HomeOps with repeatable desired-state stack, storage, backup, restore,
  upgrade, and rollback workflows before treating new application data as
  durable.

Recommended thinking level for the next work:

- Start at `medium` for container inventory, plan refinement, report review,
  and read-only storage planning.
- Use `high` for desired-state schema, controller lifecycle actions, Compose
  bundles, backup/restore logic, and cross-file implementation.
- Use `extra high` only before approval-required cleanup, storage formatting,
  firewall or routing changes, destructive stack removal, or rebuild execution.

## Current Resume State

- Check `git status --short --branch` at session start for branch cleanliness.
- Latest fleet report run: `2026-07-21T12-13-24Z`; all 3 servers collected
  without errors.
- Latest targeted `container-host` run: `2026-07-22T15-46-36Z`; sanitized
  inventory confirmed the four desired monitoring containers plus Portainer
  and Watchtower running, with no legacy monitoring containers remaining.
- Latest targeted `container-host` status: 0 critical, 0 warning, and 0
  informational findings.
- Latest fleet status: 0 critical, 1 warning, and 2 informational findings.
- `openvpn-server` has 3 non-security package updates pending; no reboot is
  required.
- Latest targeted `ispy-server` run: `2026-07-22T14-26-31Z`; AgentDVR is active,
  no package updates are pending, no reboot is required, and there are no
  findings. The previously observed five security updates and one normal update
  no longer require action; the collection does not identify what cleared them.
- `container-host` has no pending package updates with Docker active, 6 of 6
  containers running, no unhealthy containers, and no required reboot.
- `container-host` has an i5-4210U with 4 CPU threads, about 8 GB RAM, and about
  80 GB free on the root disk. Current load and memory use are low.
- The accepted direction is a LAN-only House OS combining Home Assistant,
  Mealie, Paperless-ngx, Forgejo, and a household Mission Control dashboard.
- A 1 TB USB drive can be added for larger application data and exports. Keep
  databases and latency-sensitive state on the internal disk.
- A fresh read-only `lsblk` inventory on 2026-07-22 again found only the internal
  250 GB Samsung SATA SSD; no USB storage device is attached. The implemented
  read-only `inspect_storage_devices` action completed at
  `2026-07-22T14:31:43Z` and recorded that `/srv/homeops-storage` is not mounted,
  with no USB transport detected. It will report filesystem, mount, ownership,
  and sentinel metadata once the drive is connected.
- A phone on normal home Wi-Fi must be able to scan a PDF and upload it through
  the Paperless web dashboard.
- Existing containers may be removed if sanitized inventory shows they are not
  useful.
- Sanitized Docker inventory is implemented locally in the health script,
  validated by the controller, and rendered in the dashboard, fleet catalog,
  and container review.
- Updated health script deployment completed through the approval-gated action:
  `history/actions/2026-07-20T17-12-38Z-container-host-deploy_health_script.json`.
- Current disposition recommendations: keep the four `homeops-monitoring-*`
  desired-state containers; retire Portainer and Watchtower only after
  replacements exist. The four legacy monitoring containers and two old data
  volumes were removed after rollback acceptance.
- Read-only evidence confirmed `/mnt/storage1`, `/mnt/storage2`, and
  `/mnt/storageWD320` are nearly empty directories on the 100 GB root
  filesystem, not external mounts. The host currently exposes only its internal
  250 GB Samsung SATA SSD; the planned 1 TB USB drive is not attached.
- `mysql57` has about 210 MiB in `dev-db_mysql_data`, no application network
  peer, and its database enumeration query was unavailable. The Compose file is
  under `/home/containerserver/docker_lab/dev-db/`.
- `nonprofit-postgres` has about 46 MiB in `nonprofit_postgres_data`, including
  a small `nonprofit_app` database, and no application network peer.
- The operator confirmed both databases were application-development test data
  and File Browser is empty. No backup or preservation is required for these
  three containers.
- The approved `retire_disposable_containers` action completed at
  `2026-07-20T19:12:32Z`. It removed `filebrowser`, `mysql57`, and
  `nonprofit-postgres`, their anonymous attached volume, and the named volumes
  `dashboards_filebrowser_data`, `dev-db_mysql_data`, and
  `nonprofit_postgres_data`. It did not prune Docker or delete bind-mounted
  paths, networks, or Compose files.
- Sanitized point-in-time evidence is tracked in
  `config/container-review-evidence.yaml` and rendered in the container review.
- Desired workload intent is tracked in `config/workloads.yaml`: monitoring,
  Mission Control, smart home, recipes, documents, and developer lab are ordered
  into phases with storage, backup, and acceptance prerequisites. Deployment is
  gated for every workload until pinned Compose bundles and preflights exist.
- `stacks/mission-control/` now contains the first Compose-valid draft for
  Homepage 1.13.2, Uptime Kuma 2.4.0, and ntfy 2.23.0 with committed
  Linux/amd64 digests. The starter dashboard links directly to the Grafana
  HomeOps Overview, Uptime Kuma, ntfy, and temporary Portainer access.
- Initial Mission Control ingress is defined as direct LAN-only bindings on
  `192.168.86.58`: Homepage `8081`, Uptime Kuma `3001`, and ntfy `8082`.
  Homepage has no Docker socket, ntfy defaults to deny-all, and all services
  have health, restart, resource, PID, and log limits. Deployment remains
  disabled until protected credentials are provisioned and backup/restore is
  implemented and proven.
- The corrected `preflight_mission_control_images` execution completed at
  `2026-07-22T16:49:20Z`. All three exact images, amd64 architecture, required
  tools, and the bootstrap's `bcryptjs` and `socket.io-client` dependencies
  passed. No planned container, volume, or port collisions were found. A
  read-only post-check confirmed only the same six existing containers running;
  no Mission Control service was started.
- `provision_mission_control_secrets` is implemented, registered, and dry-run
  verified. Its approved execution completed at `2026-07-22T19:14:42Z`. It
  created owner-only Uptime Kuma and ntfy admin credentials plus a regular
  `homeops` service identity, verified generated bcrypt hashes and the
  topic-scoped token without printing them, never wrote the service plaintext
  to disk, and copied three Git-ignored recovery values locally. Post-checks
  confirmed a `0700` server directory, five `0600` files owned by
  `containerserver`, no service plaintext, and three non-empty ignored local
  copies. Those copies rely on workstation/disk protection; Git-ignore is not
  encryption or an ACL.
- The tracked Uptime Kuma bootstrap is version-locked to 2.4.0 and consumes the
  admin password and scoped ntfy token only as JSON on stdin. During the future
  loopback-only first start it creates or verifies `admin`, four core monitors,
  a reconciled ntfy notification provider, monitor-to-alert associations, and
  the `homeops` status page. It handles Uptime Kuma's object-shaped status-page
  list, refuses managed-name conflicts, and does not edit SQLite directly.
  Direct LAN HTTP is temporary; local HTTPS is required before routine
  credentialed phone use.
- Four approved Mission Control acceptance starts failed closed and removed
  all candidate containers, networks, volumes, and derived runtime secrets.
  The third start proved ntfy healthy, then isolated Uptime Kuma as the only
  blocker: capability-dropped container root could not write the pinned image's
  `1000:1000`-owned `/app/data`. A bounded live probe proved the corrected
  `1000:1000` service identity reaches the first-run listener. The desired
  Compose definition and regression test now preserve that ownership contract.
  The fourth attempt made all
  three containers healthy but timed out in bootstrap because Uptime Kuma 2.4
  first served its separate database-selection UI. A bounded probe proved its
  supported `UPTIME_KUMA_DB_TYPE=sqlite` contract writes `db-config.json`, runs
  migrations, and reaches the main Socket.IO server. Desired state now records
  that non-interactive database selection. Replacing the Socket.IO client's
  timeout wrapper with a plain acknowledgement plus the same bounded timer then
  passed both first-run bootstrap and immediate reconciliation in isolation.
- The corrected fifth `deploy_mission_control_stack` execution completed at
  `2026-07-22T21:03:05Z`. Loopback bootstrap, scoped ntfy authorization, LAN
  cutover, a second idempotent bootstrap, exact images and non-root identities,
  healthy state, named volumes, protected runtime files, and fixed ports all
  passed. An independent post-check found all three containers healthy,
  Homepage returning `200`, Uptime Kuma returning its expected redirect, and
  anonymous ntfy publishing denied with `403`.
- The approved controlled reboot completed on 2026-07-22. The boot ID changed,
  all three Mission Control and four monitoring containers returned healthy,
  Homepage and Kuma's persisted `homeops` status page remained reachable, ntfy
  remained deny-by-default with the `homeops` account scoped only to
  `homeops-alerts`, Grafana returned healthy, and Prometheus remained healthy
  on its intentionally private endpoint.
- `provision_mission_control_backup_secret` and
  `backup_mission_control_stack` are implemented, registered, policy-allowed,
  and dry-run/local-test validated. The fixed backup lifecycle uses the pinned
  Uptime Kuma image to archive both stopped volumes read-only, encrypts before
  transfer, authenticates the ciphertext, rotates current plus previous only
  after workstation verification, removes plaintext staging on every exit, and
  restores healthy services through a recovery trap. Live key provisioning and
  backup remain approval-gated; destructive restore is not yet implemented.
- The operator approved a clean monitoring rebuild because the basic Grafana
  configuration and Prometheus history did not need migration. The replacement
  passed health, LAN-exposure, dashboard, reboot, and rollback acceptance; the
  old state was then removed through the bounded cleanup action.
- `docs/monitoring-stack-upgrade-review.md` is the required learning ledger for
  every old-to-new monitoring change and why it is needed.
- The live non-secret monitoring preflight completed on 2026-07-21. It confirmed
  no runtime resource limits, log rotation, security options, or intentional
  Prometheus retention; only cAdvisor has a health check. Current Grafana and
  Prometheus data total under 250 MiB, and existing cross-server scrape jobs are
  preserved in the draft.
- `stacks/monitoring/` now contains a Compose-valid clean replacement using
  Grafana 13.1.0, Prometheus 3.12.0, Node Exporter 1.11.1, and cAdvisor 0.57.0,
  plus provisioning, rules, and a HomeOps overview dashboard. The approved
  cutover and final acceptance completed on 2026-07-21; the workload is active.
- Linux/amd64 manifest digests for all four pinned monitoring images were
  resolved read-only and committed in Compose. Re-resolve them immediately
  before deployment to detect tag movement.
- `preflight_monitoring_images` is implemented as a fixed approval-gated action
  and its approved execution passed on 2026-07-21. It pulled only the four
  immutable images, checked their health tooling, validated Prometheus
  configuration/rules with pinned `promtool`, and cleaned two exact temporary
  files. A targeted post-check confirmed the same six original containers were
  still running; the host now has one non-security package update pending.
- Fixed `deploy_monitoring_stack` and `rollback_monitoring_stack` actions are
  implemented and dry-run verified. Deployment stages eight exact repository
  files, validates their hashes and the untracked Grafana secret, verifies the
  old and new identities, and automatically restores the old containers if
  cutover fails. The approved deployment passed on 2026-07-21. Rollback proves
  the old stack can restart before removing only the new candidate containers
  and volumes. The destructive rollback test and subsequent clean redeployment
  both completed successfully.
- `provision_monitoring_secret` is implemented and dry-run verified. It
  idempotently generates a 32-byte URL-safe Grafana password at the fixed
  server path, validates owner/mode/non-symlink constraints, never prints the
  value, and copies it to the Git-ignored local recovery path. Its approved
  execution passed on 2026-07-21; the local recovery file exists, is non-empty,
  and is confirmed ignored by Git.
- Independent post-cutover checks confirmed all four pinned services healthy,
  Grafana as the only LAN port, private ports 8080/9090/9100 unreachable,
  the `HomeOps Overview` dashboard provisioned, and all five Prometheus targets
  up (`prometheus`, `node-exporter`, `cadvisor`, `openvpn-server`, and
  `ispy-server`).
- Grafana's unprivileged process cannot read the host-owned `0600` secret bind
  mount. The password was immediately synchronized through Grafana's API
  without displaying it; the protected login returns 200 and the default
  returns 401. The revised lifecycle does not mount the secret. It bootstraps
  Grafana on loopback, passes the password through stdin, verifies it from the
  host, and only then exposes Grafana to the LAN.
- Grafana startup also logged bundled-plugin writes against the read-only root
  and missing optional provisioning directories. The bundle now disables
  plugin preinstall/auto-update and includes those directories.
  The first approved `repair_monitoring_grafana` attempt failed only because
  its container-side verifier could not read that `0600` file; automatic
  recovery restored the prior Compose file. All services and protected login
  remained healthy. The corrected repair is dry-run verified with loopback
  bootstrap, host-side authentication checks, Compose recovery, and guards that
  preserve cAdvisor, Node Exporter, and Prometheus identities. The second
  approved execution completed successfully. Independent checks confirmed
  clean startup, protected login, rejected `admin/admin`, the HomeOps dashboard,
  five of five targets up, only port 3000 exposed, and unchanged metric-service
  identities.
- Full regression coverage now passes with 150 tests, including executable
  Uptime Kuma collection-shape and mocked Socket.IO bootstrap contracts.
- The Git-provisioned Grafana dashboard now uses `server_id` for host legends
  and target health: `192.168.86.25:9100` maps to `openvpn-server`,
  `192.168.86.27:9100` to `ispy-server`, and `node-exporter:9100` to
  `container-host`. The generated HomeOps HTML dashboard links directly to the
  Grafana HomeOps Overview. The approved live synchronization completed, and
  the Grafana API confirmed `{{server_id}}` legends, a friendly `Server` target
  column, and hidden raw instances.
- The approved controlled `container-host` reboot completed on 2026-07-21.
  Fresh inventory confirmed all four desired monitoring containers healthy,
  all four legacy rollback containers stopped, 5/5 scrape targets up,
  protected/default authentication correct, friendly labels intact, and only
  Grafana port 3000 reachable on the LAN.
- The approved destructive rollback started all four legacy containers and
  removed the desired containers plus their new volumes. Fresh inventory proved
  that state, then the approved clean redeployment rebuilt the desired stack.
  Independent checks again confirmed protected authentication, friendly labels,
  5/5 targets, and private metric ports. Rollback acceptance is complete.
- The approved `retire_legacy_monitoring_stack` execution completed at
  `2026-07-21T20:00:36Z`. It reverified desired-state health and protected
  Grafana authentication, then removed only the four stopped legacy containers
  and two old named volumes. Final inventory shows 6 of 6 containers running;
  protected authentication, the provisioned dashboard, 5/5 targets, and the
  Grafana-only LAN boundary all still pass. Monitoring is operational.
- The approved `retire_legacy_monitoring_files` execution completed at
  `2026-07-22T14:21:38Z`. It verified the exact three-file set and healthy
  replacement stack, removed only `docker-compose.yml`, `prometheus.yml`, and
  `readme.md`, then removed the empty proof-of-concept directory. The final
  action check and targeted inventory passed.
- Exact Wi-Fi switch/garage brands, phone platform, USB enclosure, and second
  backup destination remain open inputs.
- Durable plan: `docs/container-host-house-os-plan.md`.
- `ACTIVE_WORK.md` is the single daily handoff source.
- `reports/generated/codex-brief.md` is the compact generated startup brief.
- `docs/active-operations-plan.md` was archived because it duplicated daily
  current-state and next-step guidance.
- `IMPLEMENTATION_TRACKER.md` remains the durable implementation state record.
- `docs/implementation-roadmap.md` remains the phase roadmap, not the daily
  resume source.

## Immediate Next Steps

1. Define Mission Control backup/restore and bounded deployment actions, then
   request approval for the selected direct LAN ports.
2. Add local HTTPS before routine credentialed phone access.
3. When home, attach the 1 TB USB drive and resume UUID-bound storage setup.
4. Record smart-switch and garage-controller brands/apps and phone platform.
5. Deploy in stages: Mission Control, Home Assistant, Mealie, Paperless-ngx,
   then Forgejo and an optional limited CI runner.
6. Prove reboot persistence and backup/restore for each new stateful application
   before expanding its use.

## Relevant Files

- `ACTIVE_WORK.md`: daily handoff and thinking-level guidance.
- `docs/container-host-house-os-plan.md`: accepted container-host application,
  storage, safety, and HomeOps delivery direction.
- `reports/generated/codex-brief.md`: generated compact session brief.
- `docs/codex-operating-guide.md`: Codex operating rules.
- `IMPLEMENTATION_TRACKER.md`: durable implementation status and checklist.
- `docs/implementation-roadmap.md`: long-range phase roadmap.
- `docs/archive/active-operations-plan.md`: archived current-state plan.

## Useful Commands

```powershell
python -m controller.main codex-brief
python -m controller.main collect
python -m controller.main dashboard
python -m controller.main catalog
python -m controller.main container-review --server container-host
python -m controller.main check --input history\runs\<latest-run>\fleet-health.json
python -m unittest discover -s tests
```

## Avoid By Default

- Do not start each session with a full project review.
- Do not read archived docs unless active docs are missing context.
- Do not run live fleet collection unless current server state is needed.
- Do not execute approval-required actions without exact user approval.
