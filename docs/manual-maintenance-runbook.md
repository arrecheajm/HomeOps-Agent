# Manual Maintenance Runbook

Use this runbook for one-server-at-a-time update and reboot maintenance.

The controller now has approval-gated `apply_security_updates` and
`reboot_server` actions. Manual commands remain documented for broader package
maintenance or recovery. Use either path only during an acceptable maintenance
window.

## Current Maintenance Targets

Recommended order:

1. `ispy-server`
2. `openvpn-server`
3. `container-host`

Reasoning:

- `ispy-server` has pending package updates and a reboot-required state.
- `openvpn-server` has pending package updates but no reboot-required state in
  the latest run.
- `container-host` has a reboot-required state and a restarting `watchtower`
  container, but should wait until VPN and iSpy maintenance are stable.
- `ispy-server` maintenance can interrupt camera recording or monitoring.
- `openvpn-server` maintenance can disconnect VPN clients, so handle it when VPN interruption is acceptable.
- If your current access path to the servers depends on `openvpn-server`, rebooting or breaking it can cut off access to the whole fleet.
- Prefer doing `openvpn-server` maintenance while physically on the same LAN or with a separate recovery path.
- Do not update or reboot multiple servers at the same time.

## Pre-Maintenance Checks

From the controller machine:

```powershell
python -m controller.main collect
python -m controller.main dashboard
python -m controller.main catalog
```

Review:

```text
reports/generated/index.html
```

On the target server:

```bash
hostname
whoami
uptime
who
cat /var/run/reboot-required 2>/dev/null
cat /var/run/reboot-required.pkgs 2>/dev/null
apt list --upgradable
```

Service checks:

For `ispy-server`:

```bash
systemctl status AgentDVR.service --no-pager --lines=20
systemctl is-active AgentDVR.service
systemctl is-enabled AgentDVR.service
```

For `openvpn-server`:

```bash
systemctl status openvpnas.service --no-pager --lines=20
systemctl is-active openvpnas.service
systemctl is-enabled openvpnas.service
```

Proceed only when:

- no unexpected users are logged in
- the role-specific service is active before maintenance
- you are comfortable with the outage window
- for `openvpn-server`, you have confirmed whether you are currently relying on VPN for access

## Update One Server

For security updates only, first dry-run the controller action from the
controller machine:

```powershell
python -m controller.main actions run apply_security_updates --server ispy-server --dry-run
```

Execute only after reviewing the command and supplying the exact approval phrase
printed by the dry-run.

For broader package maintenance, run on the target server:

```bash
sudo apt update
sudo apt upgrade
```

Read the package summary before accepting. If the command proposes removing important packages or changing core services unexpectedly, stop and inspect before continuing.

If packages are held back, do not force them during this pass. Record them and continue with normal verification.

## Reboot One Server

If updates complete successfully and reboot is still expected:

```powershell
python -m controller.main actions run reboot_server --server ispy-server --dry-run
```

Execute only after reviewing the delayed reboot command and supplying the exact
approval phrase printed by the dry-run. The controller action schedules a
one-minute delayed reboot.

Manual fallback on the target server:

```bash
sudo reboot
```

Wait for SSH to disconnect. Then from the controller machine, wait for it to return.

For `ispy-server`:

```powershell
ssh -i $env:USERPROFILE\.ssh\homeops_ed25519 spy@192.168.86.27 uptime
```

For `openvpn-server`:

```powershell
ssh -i $env:USERPROFILE\.ssh\homeops_ed25519 vpnserver@192.168.86.25 uptime
```

If this command fails after reboot and you were connected through VPN, stop and use your out-of-band or local network access path. Do not continue with other server maintenance until VPN access is restored.

## Post-Reboot Server Checks

On `ispy-server`:

```bash
systemctl is-active AgentDVR.service
systemctl status AgentDVR.service --no-pager --lines=20
cat /var/run/reboot-required 2>/dev/null
apt list --upgradable
```

On `openvpn-server`:

```bash
systemctl is-active openvpnas.service
systemctl status openvpnas.service --no-pager --lines=20
cat /var/run/reboot-required 2>/dev/null
apt list --upgradable
```

Expected:

- role-specific service is active
- reboot-required marker is gone, or at least understood
- pending update count is lower
- SSH works from the controller

## HomeOps Verification

From the controller machine:

```powershell
python -m controller.main collect
python -m controller.main dashboard
python -m controller.main catalog
```

Review:

```text
reports/generated/index.html
reports/generated/fleet-catalog.html
history/runs/<timestamp>/fleet-health.json
```

Expected:

- no collection errors
- maintained server no longer reports `reboot_required`
- role-specific service remains active in the HTML dashboard
- update count decreases

## iSpy Stale Service Follow-Up

Read-only discovery found:

- active service: `AgentDVR.service`
- enabled but failed unit: `ispy.service`

Do not remove or disable `ispy.service` as part of the update/reboot pass. After iSpy is updated and stable, inspect whether `ispy.service` is a stale duplicate and decide separately whether to disable it.

Useful read-only checks:

```bash
systemctl status ispy.service --no-pager --lines=20
systemctl cat ispy.service --no-pager
systemctl cat AgentDVR.service --no-pager
```

## Stop Conditions

Stop and reassess if:

- SSH does not return after reboot
- role-specific service is not active after reboot
- `apt upgrade` proposes unexpected removals
- HomeOps collection reports a collection error
- VPN access is needed before rebooting `openvpn-server`
- you are not on the local server network and have no independent recovery path for `openvpn-server`

Record findings in `docs/active-operations-plan.md` before continuing.
