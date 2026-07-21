# HomeOps Monitoring Stack

This is the reviewable replacement bundle for the current proof-of-concept
monitoring containers. It is not authorized for deployment yet.

Pinned review baseline:

- [Grafana `13.1.0`](https://github.com/grafana/grafana/releases/tag/v13.1.0)
- [Prometheus `v3.12.0`](https://github.com/prometheus/prometheus/releases/tag/v3.12.0)
- [Node Exporter `v1.11.1`](https://github.com/prometheus/node_exporter/releases/tag/v1.11.1)
- [cAdvisor `v0.57.0`](https://github.com/google/cadvisor/releases/tag/v0.57.0)

The Compose file also pins the resolved Linux/amd64 manifest digest for every
tag. The version decision and old-to-new rationale are documented in
`docs/monitoring-stack-upgrade-review.md`.

## Design

- Grafana is the only LAN-published service, bound by `HOMEOPS_LAN_IP`.
- Prometheus, Node Exporter, and cAdvisor are reachable only through the
  `homeops-monitoring` bridge network.
- Prometheus retains at most 15 days or 4 GB, whichever limit is reached first.
- Docker JSON logs rotate at 10 MB with three files per service.
- Grafana's Prometheus data source and HomeOps dashboard are provisioned from
  version-controlled files.
- The Grafana admin password is read from a server-side Docker secret file and
  is never stored in Git.
- New volume names keep this clean rebuild isolated from old rollback data.

## Local Validation

```powershell
Copy-Item .env.example .env
docker compose --env-file .env config
```

Do not create a real password in the repository. The default secret directory
is `/home/containerserver/.config/homeops/secrets/monitoring` on
`container-host`; it should be owned by `containerserver` with directory mode
`0700` and secret-file mode `0600`.

## Deployment Gate

Before any server change:

1. Re-resolve each image tag and confirm its Linux/amd64 digest still matches
   the committed value.
2. Validate Compose and Prometheus configuration.
3. Confirm all health-check commands exist in the pinned images.
4. Add a bounded HomeOps deploy/rollback action and review its dry run.
5. Keep the current monitoring containers and old volumes available until the
   new stack passes health, dashboard, LAN exposure, and reboot verification.
