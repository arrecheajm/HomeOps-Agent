# HomeOps Maintenance Report

Generated: 2026-05-04 18:30

Source run: `history/runs/2026-05-04T18-30-00`

## Fleet Summary

3 servers checked. 0 critical findings. 2 warnings. 1 informational note.

| Server | Role | Status | Notes |
|---|---|---|---|
| `openvpn-server` | VPN | Warning | 1 security update pending |
| `ispy-server` | Security Cameras | Warning | Recording disk at 84% |
| `container-host` | Containers | Warning | 1 unhealthy container |

## Critical Findings

No critical findings.

## Warnings

### iSpy recording disk usage is high

Server: `ispy-server`

Mount `/recordings` is 84% full. This is not an emergency, but recording retention should be reviewed before the disk approaches a critical threshold.

Recommended action IDs: none yet.

Risk: deleting or pruning recordings requires explicit approval.

### Docker container is unhealthy

Server: `container-host`

Container `homepage` is reporting `unhealthy`.

Recommended action ID: `restart_docker_container`

Risk: approval required.

### Security updates are pending

Server: `openvpn-server`

One security update is pending.

Recommended action ID: `apply_security_updates`

Risk: approval required.

## Informational Notes

`container-host` has 14 total pending updates, including 2 security updates. No reboot is currently required.

## Suggested Next Steps

1. Review iSpy recording retention and disk growth.
2. Approve `restart_docker_container` for `container-host` if `homepage` remains unhealthy after the next check.
3. Schedule security updates for `openvpn-server` and `container-host`.
4. Re-run collection after any approved action.

## Actions Taken

No actions executed.
