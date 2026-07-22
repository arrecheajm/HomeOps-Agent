# HomeOps Mission Control

Status: version-pinned draft; deployment is disabled until image preflight,
credential provisioning, and backup/restore design are complete.

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

- ntfy defaults to `deny-all`; deployment must refuse blank provisioned users
  and tokens even though the draft renders safely with empty values.
- Homepage's required allowed-host value is restricted to the LAN address and
  port. It has no built-in authentication, so this stack must never be exposed
  publicly.
- Uptime Kuma and ntfy use local named volumes. Neither uses the planned USB
  drive because SQLite and operational state belong on the internal SSD.
- No service has Watchtower labels. Upgrades must use reviewed image changes.
- Every service has health checks, restart policy, resource/PID ceilings, and
  bounded logs. Image preflight must prove the health commands and hardening
  options before deployment.

## Remaining Gates

1. Dry-run and separately approve the implemented
   `preflight_mission_control_images` action. It pulls only the three immutable
   images, validates architecture/tooling, and checks identity/port collisions
   without starting the stack.
2. Generate an ignored ntfy bcrypt user entry and access token without logging
   plaintext secrets; require non-empty values before deployment.
3. Define automated Uptime Kuma admin bootstrap, starter monitors, and a
   `homeops` status page. Do not leave the initial setup page exposed.
4. Choose an independent encrypted backup destination and implement exports for
   both named volumes.
5. Implement bounded deploy, health, phone-on-Wi-Fi, reboot, backup/restore, and
   rollback acceptance actions.

Local configuration validation can use:

```powershell
docker compose --env-file stacks/mission-control/.env.example -f stacks/mission-control/compose.yaml config
```
