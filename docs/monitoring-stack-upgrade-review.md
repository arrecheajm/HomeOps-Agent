# Monitoring Stack Upgrade Review

Status: operational; clean rebuild and all acceptance gates completed on
2026-07-21.

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
| Credentials | The legacy stack accepted the default Grafana admin credential. | Disable anonymous access, load a protected untracked secret, and explicitly synchronize the Grafana database password from stdin after first start. | Grafana 13 loaded the Docker secret during the clean deployment but still initialized its database with `admin/admin`; an explicit non-logging synchronization prevents a known default from surviving bootstrap or rebuild. | Required |
| Health checks | Only cAdvisor reports healthy; the other three have no reported checks. | Add service-appropriate readiness/health checks where the image supports them. | “Container running” does not prove the web API or metrics endpoint is working. | Required |
| Verification | Visual confirmation that Grafana starts. | Verify scrape targets, dashboard panels, container health, LAN-only access, and reboot persistence. | HomeOps needs objective acceptance checks before calling a deployment successful. | Required |
| Prometheus retention | Only config/data path flags are set; there is no intentional retention budget. | Limit retention to 15 days or 4 GB, whichever is reached first. | Prevent telemetry from growing until it consumes space needed by household applications. | Recommended |
| Container logging | `json-file` with no rotation options. | Rotate at 10 MB and retain three files per service. | Default JSON logs can grow without a bound even when Prometheus retention is controlled. | Recommended |
| Resource protection | No CPU, memory, or PID limits. | Use a combined ceiling of about 1.9 GB RAM and 2.5 CPU cores across the four services, then tune from observed use. | The 8 GB host must reserve capacity for Home Assistant, Paperless, Mealie, and Forgejo. | Recommended |
| Security hardening | No security options, capability drops, or read-only roots. | Use `no-new-privileges`, drop capabilities, and use read-only roots where compatible; keep a documented cAdvisor exception until host metrics are verified. | Collectors need host visibility, but that should not become unrestricted access by accident. | Recommended |
| Grafana plugins | No intentional plugin policy. | Disable bundled-plugin preinstall and automatic updates; add the optional provisioning directories to the Git bundle. | Grafana 13 attempted writes under its read-only image and logged missing-directory errors until these settings and directories were made explicit. | Recommended |
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
Host legends and the target-health table use the existing `server_id` label so
the three Node Exporter endpoints appear as `container-host`, `openvpn-server`,
and `ispy-server`; Prometheus retains the actual addresses only as backend
scrape destinations. The generated HomeOps HTML dashboard includes a direct
link to Grafana's provisioned HomeOps Overview.

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
      alerting/
        README.md
      datasources/
        prometheus.yml
      dashboards/
        dashboards.yml
      plugins/
        README.md
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
- [x] Grafana is the only monitoring service with a LAN-published port.
- [x] Grafana requires authentication and has no default credential.
- [x] Prometheus, cAdvisor, and Node Exporter are reachable only on the private
  monitoring network.
- [x] Prometheus configuration and Grafana provisioning files are read-only.
- [x] All four services report healthy and use automatic restart policies.
- [x] Prometheus reports every expected scrape target as up.
- [x] The HomeOps dashboard shows host, disk, container, and target health.
- [x] Log rotation and Prometheus retention are bounded.
- [x] The stack returns successfully after an approved host reboot.
- [x] Rollback is tested before old volumes or files are removed.
- [x] Accepted legacy containers and old data volumes are removed through the
  bounded cleanup action.

## Deployment Result

`preflight_monitoring_images` completed successfully on 2026-07-21. The pinned
images, health tooling, cAdvisor health metadata, and Prometheus configuration
all passed; a post-action collection confirmed the same six original containers
remained running.

`provision_monitoring_secret` and `deploy_monitoring_stack` completed through
their separate approval gates on 2026-07-21. The four pinned replacements are
healthy, Grafana alone is reachable at `192.168.86.58:3000`, the three raw
metric ports reject LAN connections, the HomeOps dashboard is provisioned, and
all five Prometheus targets report up.

Post-cutover authentication testing found that Grafana's unprivileged process
could not read the host-owned `0600` secret bind mount. The default was
immediately replaced through Grafana's password API without logging the secret;
the protected credential returns HTTP 200 and `admin/admin` returns 401. The
revised lifecycle keeps the secret outside the container, initially binds
Grafana to loopback, synchronizes the password from stdin, verifies both logins
from the host, and only then recreates Grafana on its LAN binding.

This follows Grafana's documented admin-password reset workflow with an
explicit `/usr/share/grafana` home path, while the pinned image's CLI adds the
non-logging `--password-from-stdin` option. See the official
[Grafana CLI documentation](https://grafana.com/docs/grafana/latest/administration/cli/).

Grafana startup logs also showed bundled-plugin write attempts against the
read-only filesystem and absent optional provisioning directories. The bundle
now disables plugin preinstall/auto-update and includes those directories.
These settings correspond to Grafana's documented `preinstall_disabled` and
`preinstall_auto_update` options in the official
[configuration reference](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/).
The first approved `repair_monitoring_grafana` attempt reached final
verification, where its container-side check could not read the `0600` host
file. Its recovery trap restored the prior Compose file; protected login,
default-login rejection, and all four service health checks remained intact.
The corrected action is dry-run verified to use loopback bootstrap and
host-side authentication, preserve the other three monitoring container
identities, and restore the prior Compose file if verification fails. Its
second approved execution completed successfully. Independent acceptance
confirmed the protected login, rejected default login, clean startup logs,
HomeOps dashboard, five of five scrape targets up, Grafana as the only exposed
monitoring port, and unchanged metric-service identities. Reboot and rollback
acceptance remained separate gates at that point.

The approved controlled host reboot completed on 2026-07-21. Fresh inventory
confirmed the four desired containers restarted healthy while the four legacy
rollback containers stayed stopped. Independent checks confirmed protected
authentication, rejected `admin/admin`, friendly `server_id` labels, 5/5
targets up, and only port 3000 reachable on the LAN. Reboot persistence is
accepted. The destructive rollback then restored all four legacy containers and
removed the desired containers plus their new volumes. A subsequent approved
clean deployment rebuilt the desired stack, and independent checks again passed
authentication, friendly labels, 5/5 targets, health, and LAN isolation.
Rollback acceptance is complete. The separately approved
`retire_legacy_monitoring_stack` action completed at
`2026-07-21T20:00:36Z` after rechecking all four desired container identities,
health checks, new volumes, protected Grafana authentication, and default-login
rejection. It removed the four stopped legacy containers and two old named
volumes. Final inventory at `2026-07-21T20-01-26Z` shows the four desired
monitoring services plus Portainer and Watchtower running, no legacy monitoring
state, no unhealthy containers, and no container-host warnings. Independent
acceptance again confirmed the HomeOps dashboard, friendly labels, 5/5 targets,
protected authentication, and only Grafana port 3000 reachable on the LAN.

The approved `retire_legacy_monitoring_files` action completed on 2026-07-22.
It required the exact non-symlink file set and healthy replacement containers,
then removed only `docker-compose.yml`, `prometheus.yml`, and `readme.md` with
non-recursive `rm` and removed the empty
`/home/containerserver/docker_lab/monitoring` directory with `rmdir`. Its final
checks and the targeted inventory at `2026-07-22T14-21-53Z` passed with 6 of 6
containers running and no findings. The monitoring migration and legacy cleanup
are complete.
