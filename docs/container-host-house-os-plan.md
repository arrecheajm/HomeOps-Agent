# Container Host House OS Plan

Status: implementation in progress.

Last updated: 2026-07-20.

## Goal

Turn `container-host` into a LAN-only "House OS" that combines:

- smart-home control and safe garage notifications
- a household document and recipe center
- a small developer lab
- the existing HomeOps monitoring and management foundation

HomeOps Agent should own the repeatable setup, verification, backup, upgrade,
rollback, and eventual rebuild workflow. Server changes remain approval-gated
and auditable through the controller.

## Confirmed Decisions

- Services are LAN-only for now. Existing OpenVPN access may provide remote
  access later without publicly exposing applications.
- A 1 TB USB drive can be added for application data and exports.
- Existing containers do not need to be preserved unless the inventory shows
  that they remain useful.
- Phones on the normal home Wi-Fi should be able to access the household apps.
- Paper documents should be scannable as PDFs on a phone and uploaded directly
  through the Paperless-ngx web interface.

## Current Host Evidence

Source run: `2026-07-20T18-33-39Z`.

- Ubuntu 24.04 on an Intel Core i5-4210U with 4 CPU threads and about 8 GB RAM.
- Root disk is about 98 GB with about 80 GB free.
- Docker is active with 9 of 9 containers running and no unhealthy containers.
- Host load and memory use are low, package maintenance is current, and no
  current host finding requires remediation.
- Sanitized inventory enumerates all 9 running containers, their images,
  restart policies, Compose identity, published ports, and mount paths.
- A read-only storage probe found only the internal 250 GB Samsung SATA SSD.
  The root logical volume is about 100 GB with about 81 GiB available.
- `/mnt/storage1`, `/mnt/storage2`, and `/mnt/storageWD320` are nearly empty
  directories backed by `/`, not mounted external disks. None has the planned
  HomeOps sentinel.

This is enough capacity for several lightweight household services. OCR and CI
jobs should be resource-limited and not intentionally scheduled together.
Large photo, media, AI, or highly parallel build workloads are outside the
initial scope.

## Target Services

### Mission Control Base

- Keep useful Prometheus, Grafana, and node-exporter monitoring.
- Add a single household dashboard such as Homepage or Homarr.
- Add Uptime Kuma for simple application reachability checks.
- Add ntfy or an equivalent local notification service.
- Use LAN-only routing. Add a friendly local name and local HTTPS after the
  first working deployment.

### Smart Home

Deploy Home Assistant Container under HomeOps management. Companion services,
such as MQTT, should be separate Compose services when a device integration
requires them.

Initial use cases:

- display and control compatible Wi-Fi switches
- show garage open/closed state
- notify when the garage remains open unexpectedly
- notify when smart devices become unavailable
- add conservative lighting automations based on time or presence
- optionally surface AgentDVR camera views

Garage safety rules:

- require a reliable open/closed sensor before automating the door
- do not initially open the garage automatically based only on presence
- require deliberate user confirmation for remote open commands
- record automation triggers and notify on unexpected or prolonged opening

Exact device support depends on the switch and garage-controller brands and
their current apps or protocols.

### Household Document And Recipe Center

Deploy Mealie first as a low-risk household service:

- recipe import and editing
- meal planning
- shared shopping lists
- phone-friendly access on the home Wi-Fi

Deploy Paperless-ngx after storage and backup verification:

- PostgreSQL and Redis on the internal disk
- originals, archival copies, thumbnails, and exports on the USB disk
- OCR, search, tags, correspondents, document types, and inbox workflows
- phone workflow: scan a multi-page PDF, open Paperless in the phone browser,
  and upload it from the dashboard
- optional later workflow: a LAN file-share inbox that Paperless consumes

Use a normal Paperless account for daily access and keep the administrative
account separate. Sensitive documents require strong credentials and local
HTTPS before the archive is treated as mature.

### Developer Lab

Deploy Forgejo for private Git repositories, issues, notes, and release files.
Add a Forgejo Actions runner only after a concrete CI use is chosen.

Runner constraints:

- one job at a time
- explicit CPU and memory limits
- no production secrets
- no unrestricted host Docker socket access
- stopped or disabled when it is not needed, if practical

The intended workload is lightweight Python, Node, documentation, HomeOps, and
Compose testing. Large builds and parallel CI are not expected on this host.

## Storage Layout

Keep latency-sensitive and frequently written state on the internal disk:

- operating system and Docker images
- Compose definitions and secrets references
- Home Assistant configuration
- PostgreSQL, Redis, SQLite, and Forgejo database state
- short-term logs and OCR temporary files

Use the 1 TB USB drive for larger durable data:

- Paperless originals, media, and exports
- Mealie exports and images
- Home Assistant backups
- Forgejo attachments, release artifacts, and optional Git LFS data
- HomeOps stack backups

Proposed mount: `/srv/homeops-storage`, using a stable filesystem UUID. Prefer
USB 3 and a Linux-native filesystem such as ext4. HomeOps should verify the
mount and a sentinel file before starting storage-dependent services so a
missing drive cannot silently redirect writes onto the root disk.

The USB drive is primary storage, not an independent backup. Irreplaceable
data needs a second copy on another drive, computer, NAS, or approved remote
backup target.

## Implementation Progress

- Sanitized Docker inventory is implemented in the read-only health script.
- The controller validates the nested container, port, and mount shapes.
- The main dashboard, fleet catalog, and container review render inventory and
  explicitly distinguish older evidence where it was not collected.
- Collection excludes logs, environment values, and labels other than Compose
  project/service identity.
- Python regression suite passes with 109 tests, and the health script passes
  Bash syntax validation.
- Deployment completed through the approval-gated action on 2026-07-20.
- Full fleet run `2026-07-20T19-14-29Z` collected the post-cleanup state with 6
  of 6 container-host containers running and no container-host findings.
- Local disposition recommendations are stored in
  `config/container-classifications.yaml` and do not trigger cleanup actions.
- Sanitized point-in-time storage and database evidence is stored in
  `config/container-review-evidence.yaml` and rendered in the focused review.
- Ordered desired workload intent is stored in `config/workloads.yaml` and
  rendered in the focused review. All deployment flags remain disabled until
  pinned Compose definitions and workload prerequisites are implemented.
- The operator confirmed File Browser is empty and both legacy databases contain
  disposable application-development test data. No backup is required for
  these three workloads.
- `retire_disposable_containers` is implemented as an approval-gated fixed
  bundle. The approved action completed on 2026-07-20, and fresh inventory
  verified 6 of 6 remaining containers with no container-host findings.
- The monitoring stack will be rebuilt from clean state rather than migrating
  the basic Grafana dashboard or Prometheus history. The old-to-new learning
  ledger and rollback plan are in `docs/monitoring-stack-upgrade-review.md`.

## Current Container Disposition

| Container | Recommendation | Reason |
|---|---|---|
| `cadvisor` | keep | Useful container metrics; later pin the image and review LAN exposure. |
| `monitoring-grafana-1` | redeploy | Start clean with provisioned data source/dashboard, authentication, a pinned image, health check, and restart policy. |
| `monitoring-node_exporter-1` | redeploy | Preserve host metrics with a pinned image, restart policy, and reviewed port binding. |
| `monitoring-prometheus-1` | redeploy | Start with clean bounded-retention storage; pin the image, add health/restart policy, and mount reviewed configuration read-only. |
| `filebrowser` | retired | Removed with its Docker volumes after the operator confirmed it was empty. Bind-mounted directories were left intact. |
| `mysql57` | retired | Removed with `dev-db_mysql_data` after the operator confirmed it was disposable test data. |
| `nonprofit-postgres` | retired | Removed with `nonprofit_postgres_data` after the operator confirmed it was disposable test data. |
| `portainer` | retire later | Overlaps with planned HomeOps management and has read-write Docker socket access. |
| `watchtower` | retire later | Replace automatic updates with pinned, approval-gated HomeOps upgrades. |

The approved cleanup removed only the three confirmed disposable containers and
their Docker data volumes. Read-only evidence confirmed that `/mnt/storage1`,
`/mnt/storage2`, and `/mnt/storageWD320` are
nearly empty directories on the root filesystem. They must not be treated as
external storage. The planned 1 TB USB drive still needs to be attached,
formatted, mounted by UUID, and protected by a sentinel preflight through an
explicit approval-gated workflow.

## HomeOps Capabilities To Add

Inventory collection is implemented locally; the remaining lifecycle items are
proposed capabilities, not currently implemented action IDs:

- [x] Sanitized Docker inventory containing container names, images, health,
  ports, restart policy, Compose project, and volume paths without logs or
  secrets.
- [x] Desired-state workload configuration in `config/workloads.yaml`.
- [x] Bounded approval-gated removal for the three confirmed disposable legacy
  containers and their named data volumes.
- [ ] Version-controlled Compose bundles under `stacks/<stack-name>/`.
- [ ] Storage preflight that validates the USB mount, sentinel, space,
  ownership, and expected directories.
- [ ] Dedicated lifecycle operations for stack preflight, deployment, backup,
  restore, upgrade, rollback, and removal.
- [ ] Health verification after deployment, upgrade, host reboot, and restore.
- [ ] Pinned application versions and controlled HomeOps upgrades. Automatic
  Watchtower updates should remain opt-in and should not be enabled for
  stateful applications without a tested backup path.
- [ ] Secrets stored outside Git and never included in reports or action
  history.

## Delivery Order

1. Inventory the 9 existing containers and classify each as keep, redeploy,
   review, or retire later. Completed on 2026-07-20 without cleanup.
2. Capture a fresh before-state snapshot before any destructive cleanup.
3. Implement desired-state stack definitions, sanitized inventory, and the
   USB-storage preflight.
4. Prepare and verify the 1 TB USB drive and the second-copy backup target.
5. Deploy the Mission Control base and verify restart behavior.
6. Deploy Home Assistant and integrate the known Wi-Fi devices conservatively.
7. Deploy Mealie and prove backup and restore.
8. Deploy Paperless-ngx, prove export and restore, then begin importing
   important documents.
9. Deploy Forgejo; add a limited runner only when needed.
10. Add all services and useful status views to the household dashboard.

## Completion Criteria

- Every retained service has a version-controlled desired-state definition.
- Every server mutation goes through an approval-gated, logged HomeOps action.
- Applications survive and verify cleanly after a host reboot.
- LAN clients can reach services, while internet clients cannot.
- The garage has conservative controls and actionable open-state alerts.
- A phone can scan and upload a document over home Wi-Fi.
- Mealie, Paperless, Home Assistant, and Forgejo each have documented and tested
  restore procedures before their data is considered durable.
- A missing USB drive prevents dependent applications from starting or writing
  into the root filesystem.

## Open Inputs For The Next Session

- Brand and app name for each Wi-Fi switch and the Wi-Fi garage controller.
- Whether the scanning phone is iPhone or Android.
- Exact 1 TB USB drive or enclosure and whether it is HDD or SSD.
- Destination for the independent second backup copy.
- Which of the current 9 containers are useful after sanitized inventory.
