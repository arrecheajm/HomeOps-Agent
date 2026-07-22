# HomeOps Mission Control

Status: image/dependency preflight and protected credential provisioning
passed. The version-pinned Uptime Kuma bootstrap and bounded acceptance deploy
and rollback actions are implemented and locally validated. Three live
acceptance starts exposed two host/container ownership boundaries and every
automatic cleanup path passed. Isolated live tests proved ntfy healthy as the
matching host identity and Uptime Kuma listening as its image data owner. The
corrected full-stack acceptance awaits fresh approval. Retained use remains
disabled until encrypted backup/restore is implemented and proven.

This internal-disk stack provides:

- Homepage at `http://192.168.86.58:8081`
- Uptime Kuma at `http://192.168.86.58:3001`
- ntfy at `http://192.168.86.58:8082`

All ports bind only to the container host's LAN address. These initial HTTP
bindings are for LAN bootstrap and acceptance, not secure routine login:
passwords and bearer tokens are not encrypted in transit. Do not reuse these
credentials elsewhere. Local DNS and HTTPS are required before routine
credentialed phone use. Homepage intentionally has no Docker socket and only
contains reviewed static links and reachability checks.

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

- ntfy defaults to `deny-all`. The interactive `admin` account remains
  separate from a regular `homeops` service user. That service user's token is
  limited to read/write access on `homeops-alerts`; it does not inherit ntfy
  administrator access. Hashes and the token are read from owner-only server
  files at container startup and are absent from Git and Docker's saved
  container environment.
- The server keeps the five source credentials owner-only. Deployment copies
  only the two ntfy hashes and scoped token into an owner-only `ntfy-runtime`
  subdirectory and mounts that directory read-only. This avoids the host's
  individual-file bind-mount permission failure without exposing the Uptime
  Kuma or ntfy administrator plaintext passwords to the container. The runtime
  copies are reconstructible, excluded from backup, and removed by acceptance
  rollback.
- ntfy runs as UID/GID `1000:1000`, matching the dedicated container-host
  account. Before first start, the bounded deploy action has Compose create the
  named volumes, then uses the pinned ntfy image with no network and minimal
  capabilities to set mode `0700` and ownership `1000:1000` on only the ntfy
  data volume. This follows ntfy's supported non-root container model and lets
  the process read the protected runtime directory and write its databases.
- Uptime Kuma also runs as UID/GID `1000:1000`, matching the ownership declared
  by its pinned image for `/app/data`. With every capability dropped, container
  root cannot bypass that directory's mode; using its actual data owner keeps
  the service writable without restoring broad root capabilities.
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

The action creates five owner-only server files: Uptime Kuma and ntfy admin
passwords, both ntfy bcrypt hashes, and the service token. It pipes a generated
service password directly into the hasher without writing that plaintext to
disk and verifies the derived hash. It also verifies the retained ntfy
admin password/hash pair without printing it and copies three ignored values
into `stacks/mission-control/secrets/`. Existing regular files are retained,
making reruns idempotent; links, empty files, wrong modes, wrong ownership,
invalid tokens, and mismatched hashes fail closed. Git-ignore prevents commits
but does not encrypt the local copies or establish a Windows ACL; the
workstation account and disk must be protected.

During the future deployment action, Uptime Kuma will first bind to loopback.
The helper reads one JSON object containing its admin password and the scoped
ntfy token from stdin, creates or verifies user `admin`, and manages four
starter HTTP monitors: Homepage, Grafana, Uptime Kuma, and ntfy. It creates or
reconciles a `HomeOps ntfy` notification provider, attaches it only to those
four monitors, and publishes them on the `homeops` status page. If a monitor
with a managed name has a different type or URL, or the managed notification
name belongs to a different provider type, bootstrap stops instead of
overwriting it. The object-shaped status-page response used by Uptime Kuma
2.4.0 is covered by an executable contract test.

## Remaining Gates

1. Run the disposable acceptance deploy, explicit rollback, and clean redeploy.
2. Implement the reviewed encrypted workstation backup contract in
   `docs/mission-control-backup-restore.md` and prove destructive restore of
   both named volumes.
3. Verify host-reboot recovery.
4. Add local HTTPS, then perform credentialed phone-on-Wi-Fi acceptance.

The deploy action intentionally treats its first generated state as
disposable. It stages only the tracked bundle, verifies hashes and protected
secrets, starts on loopback, runs the Uptime Kuma bootstrap, proves ntfy denies
anonymous and out-of-scope publishing, moves the fixed ports to the LAN, and
repeats the critical checks. Failure removes only the three candidate
containers, two candidate data volumes, and protected derived ntfy runtime
directory.

Dry-run the deploy action with:

```powershell
python -m controller.main actions run deploy_mission_control_stack --server container-host --dry-run
```

Its exact approval phrase is:

```text
Approve action deploy_mission_control_stack on container-host
```

The corrected image preflight passed at `2026-07-22T16:49:20Z`, including
explicit `bcryptjs` and `socket.io-client` dependency checks. A read-only
post-check confirmed it did not start the stack.

Protected credential provisioning passed at `2026-07-22T19:14:42Z`. Metadata
checks confirmed the protected server directory and files, absence of a
persistent service plaintext, and all three intended Git-ignored recovery
copies without reading or printing their values.

Local configuration validation can use:

```powershell
docker compose --env-file stacks/mission-control/.env.example -f stacks/mission-control/compose.yaml config
```
