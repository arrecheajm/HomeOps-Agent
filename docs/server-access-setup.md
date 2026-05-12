# Server Access Setup

Use this guide when preparing the three Ubuntu boxes for the current homelab
agent model. The goal is not to make the servers production-safe. The goal is
to make the controller's authority explicit, logged, and recoverable.

## Target Profiles

| Server | Profile | Rebuildable | Current intent |
|---|---|---:|---|
| `openvpn-server` | `guarded` | no | Preserve remote access. |
| `ispy-server` | `experimental` | yes | Diagnose, repair, or overhaul camera setup. |
| `container-host` | `lab` | yes | Disposable Docker and agent playground. |

## Local Inventory

Copy the example inventory once:

```powershell
Copy-Item config\servers.example.yaml config\servers.yaml
```

Then edit `config\servers.yaml` with real hostnames, users, identity file, and
profile fields:

```json
{
  "server_id": "ispy-server",
  "role": "ispy_server",
  "host": "192.168.86.27",
  "user": "spy",
  "identity_file": "%USERPROFILE%\\.ssh\\homeops_ed25519",
  "access_profile": "experimental",
  "rebuildable": true,
  "remote_health_command": "/opt/homeops-agent/server-scripts/common/health_summary.sh"
}
```

Allowed profiles are `guarded`, `experimental`, and `lab`. A guarded server
cannot be marked rebuildable.

## SSH Key

Use a dedicated controller key when practical:

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\homeops_ed25519 -C "homeops-controller"
```

Install the public key for the configured server user. Do not store private keys
or passwords in this repository.

## Health Script

Every server should have:

```text
/opt/homeops-agent/server-scripts/common/health_summary.sh
```

The controller can deploy this known script through the approval-gated
`deploy_health_script` action. The inventory rejects other health command paths.

Validate the generated SSH commands:

```powershell
python -m controller.main collect --dry-run
```

Run a live collection:

```powershell
python -m controller.main collect
```

## Sudoers Profiles

Templates live in:

```text
server-scripts/sudoers/
```

Use the matching template:

- `guarded.sudoers.template` for `openvpn-server`
- `experimental.sudoers.template` for `ispy-server`
- `lab.sudoers.template` for `container-host`

Install manually with:

```bash
sudo visudo -f /etc/sudoers.d/homeops-agent
```

Replace `HOMEOPS_USER` with the configured server user or a dedicated
`homeops`/`labagent` account. Confirm command paths first:

```bash
command -v unattended-upgrade
command -v systemctl
command -v shutdown
command -v bash
```

## Readiness Checks

From the controller machine:

```powershell
python -m controller.main actions list
python -m controller.main actions run apply_security_updates --server ispy-server --dry-run
python -m controller.main actions run reboot_server --server ispy-server --dry-run
python -m controller.main actions run run_admin_command --server ispy-server --command "apt-get update" --intent "refresh package metadata" --dry-run
```

Dry-runs must show the expected command and approval phrase. Do not execute live
actions until the profile and sudoers rule have been reviewed.

## Before Rebuilds

For any `rebuildable` server, capture a before-state report before destructive
work:

```powershell
python -m controller.main collect
python -m controller.main dashboard
python -m controller.main catalog
python -m controller.main before-state --server ispy-server --intent "before AgentDVR overhaul"
python -m controller.main rebuild-plan --server ispy-server --goal "rebuild AgentDVR cleanly" --strategy reinstall
```

Rebuild workflows should preserve useful config, record the plan, and require a
separate destructive approval phrase.
