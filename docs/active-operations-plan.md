# Active Operations Plan

This plan captures the current HomeOps operating focus after the first successful read-only collections.

## Current State

Enabled servers:

- `openvpn-server`
- `ispy-server`

Temporarily disabled:

- `container-host`, because it is currently offline

Latest known findings:

- `openvpn-server`: reboot required, pending package updates
- `ispy-server`: reboot required, pending package updates
- no critical findings
- no collection errors

Read-only detail gathered:

- `openvpn-server` reboot is tied to kernel packages and `linux-base`.
- `ispy-server` reboot is tied to multiple kernel image packages.
- neither enabled server reported active `who` sessions during inspection.
- `ispy-server` uses `AgentDVR.service` as the active camera service.
- `ispy-server` also has an enabled but failed legacy-looking `ispy.service` unit pointing at `/home/spy/AgentDVR/start_agent.sh`.

Review the current dashboard:

```text
reports/generated/index.html
```

## Immediate Goal

Gather targeted read-only details, perform any needed maintenance manually, and re-run collection to confirm the findings clear.

Mutating controller actions are still not implemented. Any update or reboot should be done manually after deciding the outage impact is acceptable.

## Step 1: Gather Reboot And Package Details

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

## Step 2: Discover Role-Specific Services

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

- Monitor `AgentDVR.service` in collection.
- Treat failed `ispy.service` as a manual cleanup candidate after updates/reboot, because it appears to duplicate the active AgentDVR service and has been failed since February 13, 2026.

## Step 3: Perform Manual Maintenance One Server At A Time

Use the maintenance runbook:

```text
docs/manual-maintenance-runbook.md
```

Do not update and reboot both enabled servers at the same time.

Recommended order:

1. Start with `ispy-server` if camera interruption is acceptable.
2. Apply updates manually during an acceptable maintenance window.
3. Reboot only after confirming users and service impact.
4. Wait for the server to return.
5. Re-run HomeOps collection before moving to the next server.
6. Then handle `openvpn-server` during a VPN-safe maintenance window.

VPN caution:

- rebooting `openvpn-server` can drop VPN clients
- confirm whether remote access depends on it before rebooting

iSpy caution:

- rebooting `ispy-server` can interrupt camera recording or monitoring

## Step 4: Verify After Each Server

From the controller machine:

```powershell
python -m controller.main collect
python -m controller.main dashboard
```

Then review:

```text
reports/generated/index.html
history/runs/<timestamp>/fleet-health.json
reports/generated/homeops-report-<timestamp>.md
```

Expected result after maintenance:

- reboot-required finding clears for the maintained server
- pending update count decreases
- no collection errors appear
- role-specific service remains active

## Step 5: Bring Container Host Back Into Scope

After VPN and iSpy are stable:

1. Power on or repair `container-host`.
2. Confirm SSH key authentication.
3. Install `health_summary.sh`.
4. Enable it in local `config/servers.yaml`.
5. Run:

```powershell
python -m controller.main collect --dry-run
python -m controller.main collect
```

## Backlog After Current Maintenance

- Add iSpy service detection once the real unit name is known.
- Consider role-specific scripts for OpenVPN, iSpy, and Docker.
- Decide whether to implement approval-gated actions such as `reboot_server`.
- Add action history only when mutating controller actions are implemented.
