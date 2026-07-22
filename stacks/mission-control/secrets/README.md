# Mission Control secrets

The approval-gated `provision_mission_control_secrets` action creates the live
files on `container-host` under:

`/home/containerserver/.config/homeops/secrets/mission-control/`

It also copies recovery copies of the three login credentials into this
ignored directory. Only this README is tracked. Never stage or paste the
generated files into an issue, report, action record, or terminal transcript.

Generated files:

- `uptime_kuma_admin_password`: login password for Uptime Kuma user `admin`
- `ntfy_admin_password`: login password for ntfy user `admin`
- `ntfy_access_token`: full-account ntfy token for HomeOps integrations

The server additionally retains `ntfy_password_hash`, which ntfy reads through
a read-only bind mount. All server files and this local directory are owner-only.
