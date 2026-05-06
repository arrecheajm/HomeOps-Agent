# Manual Maintenance Runbook

Use this runbook for update and reboot maintenance until controller action execution is implemented.

The controller is currently read-only. These commands are manual server operations and should be run only during an acceptable maintenance window.

## Current Maintenance Targets

Recommended order:

1. `ispy-server`
2. `openvpn-server`

Reasoning:

- Both servers have pending package updates and kernel-triggered reboot-required state.
- `ispy-server` maintenance can interrupt camera recording or monitoring.
- `openvpn-server` maintenance can disconnect VPN clients, so handle it when VPN interruption is acceptable.
- Do not update or reboot both servers at the same time.

## Pre-Maintenance Checks

From the controller machine:

```powershell
python -m controller.main collect
python -m controller.main dashboard
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

## Update One Server

Run on the target server:

```bash
sudo apt update
sudo apt upgrade
```

Read the package summary before accepting. If the command proposes removing important packages or changing core services unexpectedly, stop and inspect before continuing.

If packages are held back, do not force them during this pass. Record them and continue with normal verification.

## Reboot One Server

If updates complete successfully and reboot is still expected:

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
```

Review:

```text
reports/generated/index.html
history/runs/<timestamp>/fleet-health.json
reports/generated/homeops-report-<timestamp>.md
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

Record findings in `docs/active-operations-plan.md` before continuing.
