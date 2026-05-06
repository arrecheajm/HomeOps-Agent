# Archived: Initial Server Setup Notes

This document is archived. Use the active walkthrough instead:

```text
docs/server-setup-walkthrough.md
```

The notes below are preserved for historical context.

# Initial Server Setup

This project is not ready to mutate servers automatically. The current implementation can load inventory, show planned SSH commands, and run read-only collection if the configured scripts already exist on each server.

## Current Installation Model

For v1, install scripts deliberately on each server. The controller will not silently install them.

Recommended remote directory:

```text
/opt/homeops-agent/server-scripts/
```

Recommended first script path:

```text
/opt/homeops-agent/server-scripts/common/health_summary.sh
```

## Server User

Create or choose a limited SSH user, for example `homeops`.

That user needs read access for health checks. It should not receive broad passwordless sudo access for v1.

Some checks may return partial data without elevated permissions. That is acceptable for the first connection test.

## Manual Script Install

On each Ubuntu server, create the directory and place the script:

```bash
sudo mkdir -p /opt/homeops-agent/server-scripts/common
sudo chown -R "$USER":"$USER" /opt/homeops-agent
chmod +x /opt/homeops-agent/server-scripts/common/health_summary.sh
```

Then copy the repository script contents to:

```text
/opt/homeops-agent/server-scripts/common/health_summary.sh
```

Validate it locally on the server:

```bash
/opt/homeops-agent/server-scripts/common/health_summary.sh
```

The output should be one JSON object.

The script may emit its local hostname and role, but the controller uses `config/servers.yaml` as the source of truth for `server_id` and `role`.

## Controller Inventory

Copy the example inventory:

```bash
cp config/servers.example.yaml config/servers.yaml
```

Edit:

- `host`
- `user`
- `port`
- `role`
- `identity_file`
- `remote_health_command`

The example file uses JSON-compatible YAML so the controller can parse it without extra Python dependencies.

If using a dedicated controller SSH key, set `identity_file` to the local private key path. Environment variables and `~` are expanded by the controller before running SSH.

Windows example:

```json
"identity_file": "%USERPROFILE%\\.ssh\\homeops_ed25519"
```

Leave `identity_file` as `null` when relying on the default SSH key or an SSH config entry.

For v1, `remote_health_command` must be the approved read-only script path:

```text
/opt/homeops-agent/server-scripts/common/health_summary.sh
```

The controller rejects other command strings before building or running SSH commands.

## Connection Readiness Checklist

- [ ] `config/servers.yaml` exists and has correct hostnames or IP addresses.
- [ ] SSH key authentication works from the controller machine to each server.
- [ ] `identity_file` is set when a non-default SSH key is required.
- [ ] The configured SSH user can run the remote health command.
- [ ] `health_summary.sh` exists on each server and is executable.
- [ ] Running the health script directly on each server prints valid JSON.
- [ ] The inventory `remote_health_command` is the approved `health_summary.sh` path.
- [ ] `python -m controller.main collect --dry-run` shows the expected SSH commands.

After those pass, the repo is ready for the first real read-only collection:

```bash
python -m controller.main collect
```

## Future Deployment Command

A later implementation may add an explicit script deployment command. It should:

- copy only known files from `server-scripts/`
- require approval before writing to a server
- avoid editing system service, firewall, SSH, OpenVPN, or Docker configuration
- verify the final remote path
- record deployment attempts in action history
