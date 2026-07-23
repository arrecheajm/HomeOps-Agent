# Mission Control Backup And Restore Contract

Status: protected key provisioning completed at `2026-07-22T22:02:19Z`, the
Homepage read-only configuration repair passed live acceptance at
`2026-07-23T13:25:13Z`, and the authenticated encrypted backup and bounded
destructive restore actions are implemented and locally validated. A fresh live
backup and destructive restore proof are still required before Mission Control
may hold retained household state.

The first approved live-backup attempt on 2026-07-23 failed before archive
creation because Homepage was restarting during preflight. No encrypted export
or workstation artifact was created. Inspection isolated a missing-required-file
failure in Homepage's read-only configuration. The bounded repair subsequently
installed the three required tracked skeleton files, recreated only Homepage,
and passed API, log, health, and zero-restart acceptance. Independent container
and browser checks also passed. Backup retry remains a fresh approval boundary;
the failed backup approval is not reused.

## Lifecycle Boundary

The first deployment is an acceptance deployment. Uptime Kuma and ntfy data
created during this phase is disposable. The deploy action starts the services
on loopback, bootstraps and verifies them, moves the fixed ports to the LAN,
then repeats the important checks. Any failed deploy or verification removes
only the three new containers and two new named volumes.

The acceptance stack must not be used for irreplaceable configuration until
all of these gates pass:

1. Deploy acceptance succeeds.
2. The explicit rollback action removes the candidate containers and volumes.
3. A clean redeploy succeeds, proving bootstrap reproducibility.
4. An encrypted backup is copied to the HomeOps workstation.
5. A destructive restore drill recreates both volumes and passes the same
   health, bootstrap-idempotence, ntfy-ACL, and LAN-binding checks.

## Backup Set And Destination

The backup set is exactly:

- `homeops-mission-control_uptime-kuma-data`
- `homeops-mission-control_ntfy-data`
- a manifest containing the schema version, UTC creation time, pinned image
  references, archive names, sizes, and SHA-256 hashes

The protected `ntfy-runtime` directory is not application data and is excluded.
It contains only deploy-time copies of two hashes and the scoped token and is
reconstructed from the five owner-only source files.

The first independent destination will be the HomeOps workstation under the
Git-ignored `backups/mission-control/` directory. This is independent of a
container-host disk failure. The future 1 TB USB disk is not the first backup
destination because it is not attached yet and a disk permanently attached to
the same host is not sufficient as the only recovery copy.

## Confidentiality And Integrity

The backup must be encrypted before it leaves the protected temporary working
directory on the server. A high-entropy backup password is stored as an
owner-only server secret and retained in a Git-ignored local recovery file.
The encrypted artifact also receives an HMAC-SHA-256 sidecar generated without
placing the key in process arguments or logs. Restore verifies the HMAC before
decryption, then validates the manifest and every inner SHA-256 hash.

This design protects the workstation copy at rest and survives loss of the
container host. Because the running host needs the key for an agent-operated
backup, it does not protect against an attacker who simultaneously obtains the
server, its secret, and the backup. A later offline or separately administered
copy is required for that stronger threat model.

## Consistency And Cleanup

The backup action must stop Uptime Kuma and ntfy only after all tools, paths,
space, secrets, and destination prerequisites pass. It archives the stopped
volumes with pinned images, deletes plaintext staging on every exit path, and
restarts and health-checks both services before reporting success. Homepage
may remain running.

The restore action must reject unsafe archive members, unexpected volume names,
wrong image references, invalid hashes, and unauthenticated ciphertext before
touching live state. Immediately before replacement it creates a rollback
snapshot of the current volumes. If restore or post-restore acceptance fails,
the action restores that snapshot and restarts the prior stack.

## Retention And Proof

The initial implementation keeps one known-good encrypted backup plus one
previous encrypted backup on the workstation. An action is not considered a
successful backup until the local encrypted artifact and HMAC sidecar are both
present and non-empty. A backup is not considered proven until a destructive
restore drill completes and the resulting services pass all deployment checks.

## Implemented Backup Mechanics

- `provision_mission_control_backup_secret` creates or validates a 64-character
  master key as a `0600` regular file under the existing `0700` server secret
  directory, copies it to the ignored recovery directory, and validates the
  copy without printing it.
- Its approved execution completed at `2026-07-22T22:02:19Z`. Metadata-only
  checks confirmed the server key's regular-file, owner, mode, and format
  contract and independently validated that the recovery copy is Git-ignored.
- `backup_mission_control_stack` accepts no paths or key arguments. It uses
  fixed volume names, fixed protected staging/export paths, and the ignored
  workstation destination.
- The pinned Uptime Kuma image supplies GNU tar and reads both stopped volumes
  through read-only mounts as UID/GID `1000:1000`. The manifest records schema
  version, UTC time, immutable image references, archive names, byte sizes, and
  inner SHA-256 hashes.
- OpenSSL 3 encrypts the payload with AES-256-CBC, PBKDF2-SHA-256, a random
  salt, and 310,000 iterations. Python derives a purpose-specific HMAC key from
  the master key and authenticates the entire ciphertext with HMAC-SHA-256.
- A local helper verifies the HMAC before rotating `current` to `previous`.
  Tampered or incomplete incoming artifacts cannot replace the current pair.
- Exact-file cleanup removes plaintext staging on every remote exit. A recovery
  trap restarts Uptime Kuma and ntfy and waits for Compose health if backup
  creation fails after they stop.

## Implemented Restore Mechanics

- `restore_mission_control_stack` accepts no paths or source arguments and uses
  only the authenticated workstation `current` pair, the fixed protected server
  staging directory, and the two fixed named volumes.
- The workstation validates the HMAC before transfer. The server validates it
  again before decryption, then requires the exact schema, pinned images, volume
  names, archive names, byte sizes, and inner SHA-256 hashes.
- The validator permits only regular files and directories at safe relative
  paths. It rejects links, devices, traversal, absolute paths, duplicates,
  unexpected outer members, and malformed or incomplete manifests before
  service downtime.
- After validation, only Uptime Kuma and ntfy stop. The action creates plaintext
  rollback archives of both live volumes inside protected server staging before
  changing either volume; those temporary files never transfer to the
  workstation and are removed on every exit.
- Restore clears and repopulates each fixed volume as UID/GID `1000:1000`
  without deleting or renaming Docker volumes. It then reruns Compose health,
  idempotent Kuma bootstrap, status-page, ntfy ACL, and fixed LAN-port checks.
- Any failure after mutation stops both services, restores both pre-action
  rollback archives, restarts the stack, checks health/status/ACL, and returns a
  failed action record. Generated Bash passed `bash -n` on `container-host`
  without execution; executable valid and unsafe-archive tests pass locally.
