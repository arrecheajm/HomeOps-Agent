# Server Setup Walkthrough

Use this walkthrough while preparing and extending read-only HomeOps collection.
Pause at any step and ask Codex questions using this file as the shared checklist.

## Goal

Each Ubuntu server should reach this state:

- a limited SSH user exists, for example `homeops`
- SSH key authentication works from the controller machine
- `/opt/homeops-agent/server-scripts/common/health_summary.sh` exists
- the script is executable
- running the script prints one JSON object
- `config/servers.yaml` points to the real hosts
- `python -m controller.main collect --dry-run` shows the expected SSH commands

Do not add mutating action support during this setup. This pass is read-only collection.

## Server Status Tracker

| Server | Inventory updated | SSH key works | Script installed | Local JSON valid | Controller dry-run checked | First collect checked |
|---|---|---:|---:|---:|---:|---:|
| `openvpn-server` | yes | yes | yes | yes | yes | yes |
| `ispy-server` | yes | yes | yes | yes | yes | yes |
| `container-host` | pending | no | no | no | no | no |

Current local inventory has `container-host` disabled while that server is offline.

## Step 1: Create Local Inventory

Run this from the controller machine when starting a new local inventory:

```powershell
Copy-Item config\servers.example.yaml config\servers.yaml
```

Edit `config\servers.yaml` with real values for each server:

```json
"host": "actual-ip-or-hostname",
"user": "homeops",
"port": 22,
"identity_file": "%USERPROFILE%\\.ssh\\homeops_ed25519"
```

Keep this exact remote command path:

```text
/opt/homeops-agent/server-scripts/common/health_summary.sh
```

The controller rejects other remote health command strings.

## Step 2: Confirm Or Create SSH Key

Check existing SSH keys:

```powershell
Get-ChildItem $env:USERPROFILE\.ssh
```

If a dedicated HomeOps key is needed:

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\homeops_ed25519 -C "homeops-controller"
```

When using a dedicated key, set `identity_file` in `config/servers.yaml` so the controller includes `-i` in generated SSH commands:

```json
"identity_file": "%USERPROFILE%\\.ssh\\homeops_ed25519"
```

Leave `identity_file` as `null` only when the default SSH identity or SSH config should be used.

## Step 3: Create The Server User

Run this on each Ubuntu server as an existing admin user if you want a dedicated `homeops` account:

```bash
sudo useradd -m -s /bin/bash homeops
sudo mkdir -p /home/homeops/.ssh
sudo chmod 700 /home/homeops/.ssh
sudo touch /home/homeops/.ssh/authorized_keys
sudo chmod 600 /home/homeops/.ssh/authorized_keys
sudo chown -R homeops:homeops /home/homeops/.ssh
```

Add the controller public key to:

```text
/home/homeops/.ssh/authorized_keys
```

For v1, do not grant broad passwordless sudo to `homeops`.

Current setup uses existing users for the two enabled servers:

- `openvpn-server`: `vpnserver`
- `ispy-server`: `spy`

That is acceptable for the current read-only phase. A dedicated `homeops` user can be introduced later if you want tighter separation.

## Step 4: Install The Read-Only Script

On each server:

```bash
sudo mkdir -p /opt/homeops-agent/server-scripts/common
sudo chown -R homeops:homeops /opt/homeops-agent
```

Copy this repository file:

```text
server-scripts/common/health_summary.sh
```

To this server path:

```text
/opt/homeops-agent/server-scripts/common/health_summary.sh
```

Then make it executable:

```bash
chmod +x /opt/homeops-agent/server-scripts/common/health_summary.sh
```

## Step 5: Validate Locally On Each Server

Run as `homeops`:

```bash
sudo -u homeops /opt/homeops-agent/server-scripts/common/health_summary.sh
```

Expected result: one JSON object.

Partial data is acceptable during the first pass. Avoid adding `homeops` to privileged groups such as `docker` until that tradeoff is deliberate.

## Step 6: Validate SSH From Controller

From the controller machine, use the real hostnames or IP addresses from `config\servers.yaml`:

```powershell
ssh -i $env:USERPROFILE\.ssh\homeops_ed25519 homeops@openvpn-server.local /opt/homeops-agent/server-scripts/common/health_summary.sh
ssh -i $env:USERPROFILE\.ssh\homeops_ed25519 homeops@ispy-server.local /opt/homeops-agent/server-scripts/common/health_summary.sh
ssh -i $env:USERPROFILE\.ssh\homeops_ed25519 homeops@container-host.local /opt/homeops-agent/server-scripts/common/health_summary.sh
```

Each command should print one JSON object.

Current enabled-server examples:

```powershell
ssh -i $env:USERPROFILE\.ssh\homeops_ed25519 vpnserver@192.168.86.25 /opt/homeops-agent/server-scripts/common/health_summary.sh
ssh -i $env:USERPROFILE\.ssh\homeops_ed25519 spy@192.168.86.27 /opt/homeops-agent/server-scripts/common/health_summary.sh
```

## Step 7: Dry-Run The Controller

From the repository root:

```powershell
python -m controller.main collect --dry-run
```

Confirm each generated command points to:

- the expected host
- the expected user
- the expected SSH port
- the expected `-i` identity file, when configured
- `/opt/homeops-agent/server-scripts/common/health_summary.sh`

## Step 8: First Real Read-Only Collection Or Refresh

Only after the dry-run is correct:

```powershell
python -m controller.main collect
```

Review the generated artifacts:

```text
history/runs/<timestamp>/fleet-health.json
reports/generated/homeops-report-<timestamp>.md
reports/generated/index.html
```

If collection fails for one server, keep the raw result in `history/runs/<timestamp>/raw/<server_id>.json` and ask Codex to inspect it before changing server permissions.

## Questions To Ask Codex While Working

- "I am on Step 1. Does this `config/servers.yaml` entry look right?"
- "I am on Step 3 for `openvpn-server`. Is this user setup safe?"
- "The script output from Step 5 looks odd. Is this valid JSON?"
- "The SSH command in Step 6 fails. What should I check next?"
- "Here is the dry-run output from Step 7. Is it safe to run collect?"
- "Here is the generated report. What should I do next?"
