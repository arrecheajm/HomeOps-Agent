# Active Operations Plan

Archived: use `ACTIVE_WORK.md` for current daily handoff and next-step
guidance. This file is kept only for historical context.

This plan captures the current HomeOps operating focus after pivoting the fleet
from a conservative home-infra framing to a personal homelab agent controller.

## Current State

Enabled servers:

- `openvpn-server`: `guarded`, not rebuildable, preserve VPN access
- `ispy-server`: `experimental`, rebuildable, diagnose or overhaul camera setup
- `container-host`: `lab`, rebuildable, Codex lab with full logged sudo

Connection state:

- `container-host` is back online at `192.168.86.58`
- local inventory uses `containerserver@192.168.86.58`
- SSH key authentication works
- the approved health script is installed
- full controller collection now succeeds for all three servers
- role-aware collection was verified on May 10, 2026, with inventory
  `server_id` and `role` passed into the health script
- the current `health_summary.sh` script was deployed to all three servers
  through the approval-gated `deploy_health_script` action on May 10, 2026
- collection after deployment refreshed the dashboard and fleet catalog

Latest targeted `container-host` findings from run `2026-05-26T19-38-51Z`:

- `container-host`: no critical, warning, or info findings
- pending package updates cleared
- reboot-required cleared
- Docker is active with no unhealthy containers
- Watchtower is running as `nickfedor/watchtower`
- sudoers profile is installed and controller sudo actions work

Latest retained non-targeted findings from older successful evidence:

- `openvpn-server`: 53 package updates pending and reboot required in latest
  retained evidence
- `ispy-server`: reboot required, 71 package updates pending, and failed legacy
  `ispy` service in latest retained evidence
- no critical findings
- no collection errors

Read-only detail gathered:

- Earlier inspection tied the previous `openvpn-server` reboot-required state
  to kernel packages and `linux-base`; the latest run no longer reports reboot
  required there.
- `openvpn-server` role-aware service collection reports `ssh` and `openvpnas`.
- `ispy-server` reboot is tied to multiple kernel image packages.
- `ispy-server` role-aware service collection reports `ssh` and `AgentDVR`.
- `container-host` role-aware service collection reports `ssh` and `docker`.
- fleet catalog hardware details now include architecture, CPU model, memory
  total, virtualization, and disk sizes.
- none of the enabled servers reported active `who` sessions during inspection.
- `ispy-server` uses `AgentDVR.service` as the active camera service.
- `ispy-server` also has an enabled but failed legacy-looking `ispy.service` unit pointing at `/home/spy/AgentDVR/start_agent.sh`.

Review the current dashboard:

```text
reports/generated/index.html
```

## Immediate Goal

Keep `openvpn-server` stable as the access box, use `ispy-server` as the
intermediate repair/overhaul target, and use `container-host` as the Codex lab
box with full logged sudo.

Only narrow approval-gated controller actions are implemented.
Docker inspection/replacement/migration, service restarts, health script
deployment, sudoers deployment, package updates, security updates, delayed
reboots, and logged admin commands require exact approval and write action
history. Review dry-runs before any live maintenance window.

## Step 1: Maintain Access Profile Setup

1. Decide whether to create a dedicated `homeops` or `labagent` user on each
   server, or continue with the current per-server users.
2. Install the matching sudoers profile manually from `server-scripts/sudoers/`.
3. Keep `openvpn-server` on the guarded template.
4. Use the experimental template for `ispy-server`.
5. Keep the lab template on `container-host`; this is the disposable Codex lab
   box and grants broad sudo. The controller verified this on May 26, 2026.

## Step 2: Gather Reboot And Package Details

Run these read-only commands on each enabled server:

```bash
cat /var/run/reboot-required 2>/dev/null
cat /var/run/reboot-required.pkgs 2>/dev/null
apt list --upgradable
who
```

Purpose:

- identify which packages triggered reboot-required state
- see all pending package updates
- confirm whether users are currently logged in before maintenance

## Step 3: Discover Role-Specific Services

VPN service detection currently sees `openvpnas`.

iSpy service detection has identified `AgentDVR.service` as the active camera service. If re-checking later, run:

```bash
systemctl list-units --type=service --state=running
systemctl list-unit-files | grep -Ei 'ispy|agent|dvr|camera|mono|dotnet'
```

Purpose:

- identify the real iSpy or camera service unit name
- decide whether to add it to `server-scripts/common/health_summary.sh`
- improve future reports so service health reflects the actual role

Current follow-up:

- Monitor `AgentDVR.service` in collection. The controller now passes the
  inventory role into `health_summary.sh`, so service checks are selected by
  server role.
- Keep the deployed `health_summary.sh` in place unless a future script change
  needs another reviewed `deploy_health_script` run.
- Use `restart_service` only for approved units such as `AgentDVR.service`,
  `openvpnas.service`, or `docker.service`, and only after reviewing a dry-run.
- Treat failed `ispy.service` as a manual cleanup candidate after updates/reboot, because it appears to duplicate the active AgentDVR service and has been failed since February 13, 2026.

## Step 4: Perform Maintenance One Server At A Time

Use the maintenance runbook:

```text
docs/manual-maintenance-runbook.md
```

Do not update and reboot multiple enabled servers at the same time.

Recommended order:

1. Start with `ispy-server` if camera interruption is acceptable.
2. Apply updates during an acceptable maintenance window. Use the
   approval-gated `apply_security_updates` action only after reviewing a dry-run,
   or continue with manual updates if broader package maintenance is intended.
3. Reboot only after confirming users and service impact. Use the approval-gated
   `reboot_server` action only after reviewing a dry-run for that server.
4. Wait for the server to return.
5. Re-run HomeOps collection before moving to the next server.
6. Then handle `openvpn-server` only during a VPN-safe maintenance window, ideally while local to the server network.

VPN caution:

- rebooting `openvpn-server` can drop VPN clients
- confirm whether remote access depends on it before rebooting
- if your current access path depends on the VPN server, rebooting or breaking `openvpn-server` can cut off access to all managed servers
- only perform VPN-impacting maintenance when you are on the same LAN as the servers or have a separate recovery path

iSpy caution:

- rebooting `ispy-server` can interrupt camera recording or monitoring

## Step 5: Verify After Each Server

From the controller machine:

```powershell
python -m controller.main collect
python -m controller.main dashboard
python -m controller.main catalog
```

Then review:

```text
reports/generated/index.html
reports/generated/fleet-catalog.html
history/runs/<timestamp>/fleet-health.json
```

Expected result after maintenance:

- reboot-required finding clears for the maintained server
- pending update count decreases
- no collection errors appear
- role-specific service remains active

## Step 6: Operate The Codex Lab

`container-host` is the Codex lab. Use it for full-sudo experiments after
reviewing dry-runs and exact approval phrases:

1. Use `inspect_docker_container` for container status, logs, and compact
   `docker inspect` data.
2. Use `migrate_watchtower_container` if Watchtower regresses to the archived
   `containrrr/watchtower` Docker API mismatch.
3. Dry-run the approved action before execution:

```powershell
python -m controller.main actions run inspect_docker_container --server container-host --container watchtower --dry-run
```

4. Use `run_admin_command` for package installs, lab setup, destructive tests,
   and rebuild experiments on this host only.
5. Execute only after the user approves the exact phrase printed by the dry-run.
6. Keep `container-host` enabled in local `config/servers.yaml`.
7. Refresh collection after any lab change:

```powershell
python -m controller.main collect
```

## Backlog After Current Maintenance

- Keep `knowledge/fleet-catalog.json` refreshed after meaningful collection
  changes.
- Use `run_admin_command` dry-runs for controlled experiments on `ispy-server`
  and full-sudo lab work on `container-host`.
- Capture `before-state` snapshots before any rebuild or overhaul plan.
- Generate `rebuild-plan` drafts for rebuildable servers before destructive
  execution design.
- Add role-specific scripts for OpenVPN, iSpy, and Docker after the access
  profile model is validated.
