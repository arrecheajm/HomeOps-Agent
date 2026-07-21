# HomeOps Monitoring Stack

This is the deployed desired-state replacement for the proof-of-concept
monitoring containers. Cutover completed on 2026-07-21; the old containers and
volumes remain available only until the approved final legacy cleanup runs.

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
- Host panels and target health use the existing `server_id` labels, mapping
  the scrape endpoints to `container-host`, `openvpn-server`, and `ispy-server`
  instead of displaying internal addresses. The generated HomeOps HTML
  dashboard links directly to Grafana's HomeOps Overview.
- Grafana plugin preinstall and automatic plugin updates are disabled so its
  read-only image remains immutable.
- The Grafana admin password remains in a server-side `0600` file outside the
  container and Git. The lifecycle passes it through stdin during a loopback
  bootstrap, verifies authentication, and only then exposes Grafana to the LAN.
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

## Deployment And Acceptance Status

Before any server change:

1. Re-resolve each image tag and confirm its Linux/amd64 digest still matches
   the committed value.
2. Validate Compose and Prometheus configuration.
3. Confirm all health-check commands exist in the pinned images.
4. Dry-run and separately approve `provision_monitoring_secret`. It creates or
   validates the server-side secret with directory mode `0700` and file mode
   `0600`, never prints the value, and retains an ignored local recovery copy.
   This gate completed successfully on 2026-07-21.
5. The fixed `deploy_monitoring_stack` action completed successfully. Health,
   dashboard provisioning, five scrape targets, authentication, and LAN port
   isolation passed.
6. Acceptance found Grafana plugin-preinstall, optional-directory, and
   unreadable secret-mount startup errors. The first approved repair safely
   restored the prior Compose file when its verifier reproduced the secret
   permission problem. The corrected loopback/bootstrap repair is dry-run
   verified, approved, and completed with all acceptance checks passing.
7. Controlled reboot persistence, destructive rollback, and subsequent clean
   redeployment passed on 2026-07-21. Final removal of the stopped legacy
   containers and old volumes remains a separate approval-gated action.
