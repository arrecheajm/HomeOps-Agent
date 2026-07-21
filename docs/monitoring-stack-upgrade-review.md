# Monitoring Stack Upgrade Review

Status: clean rebuild selected; implementation and cutover not started.

This document is the learning record for replacing the current cAdvisor,
Grafana, Node Exporter, and Prometheus deployment. It lists what is different in
the proposed HomeOps stack, why each difference matters, and how the migration
will stay reversible.

## Decision

Rebuild the monitoring stack from clean, version-controlled configuration.
Do not migrate the current Grafana database, dashboards, users, or Prometheus
time-series history. The operator confirmed that Grafana was only a basic proof
of concept and that starting over is acceptable.

Keep the current four containers running until the replacement bundle passes
local validation. During cutover, retain the old Docker volumes for a short
rollback window; remove them only through a separate approved cleanup after the
new stack survives verification and a host reboot.

## Evidence And Limits

Confirmed by sanitized inventory from fleet run `2026-07-20T19-14-29Z`:

| Service | Current image | Restart | Published ports | Persistent/config mounts |
|---|---|---|---|---|
| cAdvisor | `gcr.io/cadvisor/cadvisor:latest` | `unless-stopped` | `8080` on IPv4 and IPv6 | Read-only host, sysfs, Docker, and runtime mounts |
| Grafana | `grafana/grafana:latest` | none | `3000` on IPv4 and IPv6 | `monitoring_grafana-data` |
| Node Exporter | `prom/node-exporter:latest` | none | `9100` on IPv4 and IPv6 | none reported |
| Prometheus | `prom/prometheus:latest` | none | `9090` on IPv4 and IPv6 | Writable `prometheus.yml`; `monitoring_prometheus-data` |

All four containers currently share the `monitor` Docker network with
Portainer. Grafana, Prometheus, and Node Exporter have no health check.

A follow-up sanitized inspection on `2026-07-21` confirmed:

- no CPU, memory, or PID limits on any monitoring service
- Docker's `json-file` logging driver with no rotation options
- no `security_opt`, capability drop, or read-only container root filesystem
- no Grafana environment configuration or provisioning mounts
- Prometheus only specifies its config and data paths, so retention uses image
  defaults rather than an intentional HomeOps budget
- useful 15-second scrape jobs for local Node Exporter, cAdvisor,
  `openvpn-server` at `192.168.86.25:9100`, and `ispy-server` at
  `192.168.86.27:9100`
- about 50 MiB of Grafana data and 194 MiB of Prometheus data
- no secret-bearing environment keys in the effective Compose services
- the proposed `wget` checks work in the currently running Grafana, Prometheus,
  and Node Exporter image families, while cAdvisor's image-native health check
  reports healthy; the exact pinned images still require validation after an
  approval-gated pull

The current Compose files remain on the server at
`/home/containerserver/docker_lab/monitoring/`. File contents were sanitized
through `docker compose config`; credential values and arbitrary environment
values were not collected.

## Pinned Review Baseline

The first repository draft uses the latest stable releases visible in the
projects' official release channels on `2026-07-21`:

- [Grafana 13.1.0](https://github.com/grafana/grafana/releases/tag/v13.1.0)
- [Prometheus 3.12.0](https://github.com/prometheus/prometheus/releases/tag/v3.12.0)
- [Node Exporter 1.11.1](https://github.com/prometheus/node_exporter/releases/tag/v1.11.1)
- [cAdvisor 0.57.0](https://github.com/google/cadvisor/releases/tag/v0.57.0)

These exact tags prevent accidental major/minor drift. Their Linux/amd64
manifest digests were resolved read-only from `container-host` and committed in
`stacks/monitoring/compose.yaml`; they must be rechecked immediately before
deployment so a moved tag is detected. The cAdvisor image moves from the legacy
GCR path to the project's current GHCR path for releases newer than 0.53.

## Upgrade Ledger

| Area | Current setup | Proposed HomeOps setup | Why change it | Priority |
|---|---|---|---|---|
| Ownership | Runtime containers and a remote Compose directory are the practical source of truth. | Store the reviewed bundle under `stacks/monitoring/` in this repository. | A rebuild should come from audited files rather than memory or leftover Docker state. | Required |
| Image versions | Every image uses `latest`. | Pin an exact supported version and record the resolved digest for each image. | Recreating `latest` can silently install a different release and make rollback unreliable. | Required |
| Data migration | Basic Grafana state and Prometheus history exist but are not valuable. | Start with new Grafana and Prometheus volumes. Retain old volumes only during the rollback window. | Avoid carrying accidental settings forward while preserving a short emergency rollback path. | Required |
| Restart behavior | Only cAdvisor restarts automatically. | Use `unless-stopped` for all four services. | Monitoring should recover after a host reboot without manual intervention. | Required |
| LAN exposure | Ports 3000, 8080, 9090, and 9100 listen on all IPv4 and IPv6 interfaces. | Publish only Grafana, bound to the container host's LAN address. Keep metric endpoints on a private Compose network. | Household users need Grafana; direct access to raw collectors and Prometheus is unnecessary exposure. | Required |
| Prometheus configuration | The bind-mounted `prometheus.yml` is writable by the container. | Store it in Git and mount it read-only. | The running service should not be able to mutate its desired configuration. | Required |
| Grafana provisioning | Dashboard and data-source setup is mostly manual. | Provision the Prometheus data source and the initial HomeOps dashboard from files. | A clean deployment should reproduce the useful dashboard automatically and make changes reviewable. | Required |
| Credentials | Not confirmed. | Disable anonymous/admin defaults and load the initial admin secret from an untracked server-side environment file. | Credentials must not live in Compose, Git, reports, or action history. | Required |
| Health checks | Only cAdvisor reports healthy; the other three have no reported checks. | Add service-appropriate readiness/health checks where the image supports them. | “Container running” does not prove the web API or metrics endpoint is working. | Required |
| Verification | Visual confirmation that Grafana starts. | Verify scrape targets, dashboard panels, container health, LAN-only access, and reboot persistence. | HomeOps needs objective acceptance checks before calling a deployment successful. | Required |
| Prometheus retention | Only config/data path flags are set; there is no intentional retention budget. | Limit retention to 15 days or 4 GB, whichever is reached first. | Prevent telemetry from growing until it consumes space needed by household applications. | Recommended |
| Container logging | `json-file` with no rotation options. | Rotate at 10 MB and retain three files per service. | Default JSON logs can grow without a bound even when Prometheus retention is controlled. | Recommended |
| Resource protection | No CPU, memory, or PID limits. | Use a combined ceiling of about 1.9 GB RAM and 2.5 CPU cores across the four services, then tune from observed use. | The 8 GB host must reserve capacity for Home Assistant, Paperless, Mealie, and Forgejo. | Recommended |
| Security hardening | No security options, capability drops, or read-only roots. | Use `no-new-privileges`, drop capabilities, and use read-only roots where compatible; keep a documented cAdvisor exception until host metrics are verified. | Collectors need host visibility, but that should not become unrestricted access by accident. | Recommended |
| Watchtower | Automatic updates remain available on the host. | Do not label this stack for Watchtower updates. Upgrade only through a pinned HomeOps change. | Automatic replacement defeats version pinning, validation, and rollback. | Required |
| HTTPS and friendly name | Grafana is reached directly by host and port. | Keep initial access LAN-only; add local DNS and HTTPS with the common household ingress later. | Centralizing certificates and names is cleaner than solving TLS separately for every first deployment. | Later |

## Intended Dashboard

The new Grafana dashboard should be useful rather than decorative. Its first
version should answer these questions at a glance:

- Is the server up, and how long has it been running?
- Are CPU load, memory, swap, temperature, or disk use becoming a problem?
- Is the root filesystem filling unexpectedly?
- Is `/srv/homeops-storage` mounted, and how much space remains once the USB
  drive is added?
- Which containers are running, restarting, unhealthy, or consuming unusual
  CPU and memory?
- Are Prometheus scrape targets healthy?
- Are the planned household applications reachable?

Use a small number of readable panels with plain labels. Avoid importing a huge
community dashboard without reviewing its queries and data requirements.

## Proposed Repository Bundle

```text
stacks/monitoring/
  compose.yaml
  README.md
  .env.example
  prometheus/
    prometheus.yml
    rules/
      host.rules.yml
  grafana/
    provisioning/
      datasources/
        prometheus.yml
      dashboards/
        dashboards.yml
    dashboards/
      homeops-overview.json
```

The real `.env` or secret file stays on the server and outside Git. Generated
Grafana state and Prometheus time-series data stay in named Docker volumes.

## Migration And Rollback Plan

1. Revalidate the non-secret preflight immediately before cutover so container
   identities and source files cannot drift unnoticed.
2. Re-resolve the selected exact tags and confirm their Linux/amd64 digests
   still match the committed values; review image release notes.
3. Validate the repository bundle with `docker compose config`, Prometheus
   tooling, and the exact image health commands; do not deploy an unrendered or
   untested template.
4. Review the implemented bounded HomeOps deployment and rollback actions. They
   use exact container, file, image, and volume allowlists and require separate
   approvals.
5. During approved cutover, verify the old four container identities, stop them,
   and start the new stack with new volume names.
6. Confirm all four health checks, all Prometheus targets, the HomeOps dashboard,
   LAN access to Grafana, and lack of LAN access to ports 8080, 9090, and 9100.
7. Reboot through the normal approval gate and verify the stack returns without
   manual intervention.
8. Keep the old containers stopped and old volumes intact during a short
   rollback window. Roll back by stopping the new stack and restarting the old
   known containers if acceptance fails.
9. Remove old containers, volumes, and obsolete remote Compose files only in a
   later bounded cleanup action after the new stack is accepted.

## Acceptance Checklist

- [x] All images use reviewed exact versions and recorded Linux/amd64 digests.
- [x] `docker compose config` succeeds with no secrets printed or committed.
- [ ] Grafana is the only monitoring service with a LAN-published port.
- [ ] Grafana requires authentication and has no default credential.
- [ ] Prometheus, cAdvisor, and Node Exporter are reachable only on the private
  monitoring network.
- [ ] Prometheus configuration and Grafana provisioning files are read-only.
- [ ] All four services report healthy and use automatic restart policies.
- [ ] Prometheus reports every expected scrape target as up.
- [ ] The HomeOps dashboard shows host, disk, container, and target health.
- [ ] Log rotation and Prometheus retention are bounded.
- [ ] The stack returns successfully after an approved host reboot.
- [ ] Rollback is tested before old volumes or files are removed.

## What This Does Not Yet Authorize

The first version-controlled bundle now exists at `stacks/monitoring/`, but this
decision does not authorize stopping or deleting the current monitoring
containers, removing volumes, writing remote files, changing ports, or deploying
the replacement. Those remain approval-gated HomeOps actions after the bundle
and dry run are ready for review.

`preflight_monitoring_images` completed successfully on 2026-07-21. The pinned
images, health tooling, cAdvisor health metadata, and Prometheus configuration
all passed; a post-action collection confirmed the same six original containers
remained running.

`deploy_monitoring_stack` and `rollback_monitoring_stack` are now implemented
and dry-run verified. Neither has been executed. Deployment still requires the
server-side Grafana secret and the exact phrase `Approve action
deploy_monitoring_stack on container-host`. Rollback has its own separate exact
approval. The old containers and old volumes remain untouched until a future
approved cutover.
