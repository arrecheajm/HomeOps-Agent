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

All four containers currently share the `monitor` Docker network. Grafana,
Prometheus, and Node Exporter have no reported health check.

A deeper read-only inspection attempted on `2026-07-21` timed out before SSH
connected. Therefore current resource limits, log rotation, security options,
Prometheus retention, scrape jobs, and Compose-file contents are not claimed as
facts here. They must be captured or treated as unknown before cutover.

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
| Prometheus retention | Not confirmed. | Set a modest time and size budget appropriate for the internal disk. | Prevent telemetry from growing until it consumes space needed by household applications. | Recommended |
| Container logging | Not confirmed. | Configure Docker log rotation for each service. | Default JSON logs can grow without a bound even when Prometheus retention is controlled. | Recommended |
| Resource protection | Not confirmed. | Add conservative memory, CPU, and PID limits after measuring normal use. | The 8 GB host must reserve capacity for Home Assistant, Paperless, Mealie, and Forgejo. | Recommended |
| Security hardening | Current capability and root-filesystem settings are not confirmed. | Use `no-new-privileges`, drop capabilities, and use read-only roots where compatible; document exceptions for host collectors. | Collectors need host visibility, but that should not become unrestricted access by accident. | Recommended |
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

1. Reconnect to `container-host` and repeat the non-secret preflight for current
   Compose paths, scrape targets, limits, logging, volume sizes, and image IDs.
2. Select supported image versions from official release documentation and pin
   versions plus resolved digests.
3. Build the repository bundle and validate it locally with `docker compose
   config`; do not deploy from an unrendered template.
4. Add a bounded HomeOps deployment action with an exact container, file, and
   volume allowlist. Produce and review its dry run.
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

- [ ] All images use reviewed exact versions and recorded digests.
- [ ] `docker compose config` succeeds with no secrets printed or committed.
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

This decision does not authorize stopping or deleting the current monitoring
containers, removing volumes, writing remote files, changing ports, or deploying
the replacement. Those remain approval-gated HomeOps actions after the bundle
and dry run are ready for review.
