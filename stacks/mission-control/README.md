# HomeOps Mission Control

Status: image preflight passed; protected credential provisioning and the
version-pinned Uptime Kuma bootstrap are implemented and dry-run validated.
Deployment remains disabled until credentials are provisioned and independent
backup/restore is designed and proven.

This internal-disk stack provides:

- Homepage at `http://192.168.86.58:8081`
- Uptime Kuma at `http://192.168.86.58:3001`
- ntfy at `http://192.168.86.58:8082`

All ports bind only to the container host's LAN address. Local DNS and HTTPS
belong to the later common-ingress phase. Homepage intentionally has no Docker
socket and only contains reviewed static links and reachability checks.

## Pinned Baseline

- [Homepage `v1.13.2`](https://github.com/gethomepage/homepage/releases/tag/v1.13.2), Linux/amd64 digest
  `sha256:c881120b024d6a8e2f3c9664efc568984e4352e47df459d6b32e225374c71955`
- [Uptime Kuma `2.4.0`](https://github.com/louislam/uptime-kuma/releases/tag/2.4.0), Linux/amd64 digest
  `sha256:7e26105b7c8445474a310131590bbfe619e955ed308b5af7e3f0a324bb40ea4d`
- [ntfy `v2.23.0`](https://github.com/binwiederhier/ntfy/releases/tag/v2.23.0), Linux/amd64 digest
  `sha256:33c067491862f2b302bb5a4571fa0e5a55721ef36d41820979c40533192deaec`

The digests were resolved read-only on 2026-07-22. Re-resolve them immediately
before deployment to detect tag movement.

## Security And Lifecycle Decisions

- ntfy defaults to `deny-all`. Its bcrypt hash and 32-character access token
  are read from owner-only files at container startup; neither value is stored
  in Git or Docker's saved container environment.
- Homepage's required allowed-host value is restricted to the LAN address and
  port. It has no built-in authentication, so this stack must never be exposed
  publicly.
- Uptime Kuma and ntfy use local named volumes. Neither uses the planned USB
  drive because SQLite and operational state belong on the internal SSD.
- No service has Watchtower labels. Upgrades must use reviewed image changes.
- Every service has health checks, restart policy, resource/PID ceilings, and
  bounded logs. Image preflight must prove the health commands and hardening
  options before deployment.
- Uptime Kuma does not publish a stable declarative bootstrap interface. The
  tracked helper therefore targets only the pinned 2.4.0 Socket.IO events and
  must be revalidated before every Uptime Kuma upgrade. It never edits the
  application's SQLite database directly.

## Credential And Bootstrap Workflow

Dry-run the protected provisioning action:

```powershell
python -m controller.main actions run provision_mission_control_secrets --server container-host --dry-run
```

After reviewing it, the exact approval phrase is:

```text
Approve action provision_mission_control_secrets on container-host
```

The action creates four owner-only server files, checks the bcrypt hash against
the plaintext ntfy password without printing either, and copies three ignored
login/recovery values into `stacks/mission-control/secrets/`. Existing regular
files are retained, making reruns idempotent; links, empty files, wrong modes,
wrong ownership, invalid tokens, and mismatched hashes fail closed.

During the future deployment action, Uptime Kuma will first bind to loopback.
The helper reads its admin password from stdin, creates or verifies user
`admin`, and manages four starter HTTP monitors: Homepage, Grafana, Uptime Kuma,
and ntfy. It creates or reconciles the `homeops` status page. If a monitor with
a managed name has a different type or URL, bootstrap stops instead of
overwriting the user's monitor.

## Remaining Gates

1. Approve and execute protected Mission Control credential provisioning.
2. Choose an independent encrypted backup destination and implement exports for
   both named volumes.
3. Implement bounded deploy, health, phone-on-Wi-Fi, reboot, backup/restore, and
   rollback acceptance actions.

The approved image preflight passed on 2026-07-22. It pulled all three exact
images, verified their required tools and amd64 architecture, found no planned
identity, volume, or LAN-port collisions, and did not start the stack.

Local configuration validation can use:

```powershell
docker compose --env-file stacks/mission-control/.env.example -f stacks/mission-control/compose.yaml config
```
