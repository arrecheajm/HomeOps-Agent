# Active Operations Plan

This plan captures the current HomeOps operating focus after pivoting the fleet
from a conservative home-infra framing to a personal homelab agent controller.

## Current State

Enabled servers:

- `openvpn-server`: `guarded`, not rebuildable, preserve VPN access
- `ispy-server`: `experimental`, rebuildable, diagnose or overhaul camera setup
- `container-host`: `lab`, rebuildable, disposable Docker and agent playground

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

Latest known findings from run `2026-05-12T17-16-00Z`:

- `openvpn-server`: 53 package updates pending, no reboot required
- `ispy-server`: reboot required, 71 package updates pending, failed legacy
  `ispy` service
- `container-host`: reboot required, `watchtower` container restarting
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

Keep `openvpn-server` stable as the access box, then use `ispy-server` as the
first experimental repair/overhaul target and `container-host` as the lab box.

Only narrow approval-gated controller actions are implemented.
`restart_docker_container`, `restart_service`, `apply_security_updates`, and
`reboot_server` require exact approval and write action history. Review dry-runs
before any live maintenance window.

## Step 1: Finish Access Profile Setup

1. Decide whether to create a dedicated `homeops` or `labagent` user on each
   server, or continue with the current per-server users.
2. Install the matching sudoers profile manually from `server-scripts/sudoers/`.
3. Keep `openvpn-server` on the guarded template.
4. Use the experimental template for `ispy-server`.
5. Use the lab template only on `container-host` if broad agent experimentation
   is acceptable.

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

## Step 6: Monitor Container Host

After VPN and iSpy are stable:

1. Review the `watchtower` container restart loop.
2. Dry-run the approved action if a restart is the intended next step:

```powershell
python -m controller.main actions run restart_docker_container --server container-host --container watchtower --dry-run
```

3. Execute only after the user approves the exact phrase printed by the dry-run.
4. Keep `container-host` enabled in local `config/servers.yaml`.
5. Refresh collection after any manual container maintenance:

```powershell
python -m controller.main collect
```

## Backlog After Current Maintenance

- Keep `knowledge/fleet-catalog.json` refreshed after meaningful collection
  changes.
- Use `run_admin_command` dry-runs for profile-gated experiments on
  `ispy-server` and `container-host`.
- Capture `before-state` snapshots before any rebuild or overhaul plan.
- Generate `rebuild-plan` drafts for rebuildable servers before destructive
  execution design.
- Add role-specific scripts for OpenVPN, iSpy, and Docker after the access
  profile model is validated.
