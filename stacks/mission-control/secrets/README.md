# Mission Control secrets

The approval-gated `provision_mission_control_secrets` action creates the live
files on `container-host` under:

`/home/containerserver/.config/homeops/secrets/mission-control/`

It also copies recovery copies of three credentials into this ignored
directory. Only this README is tracked. Never stage or paste the generated
files into an issue, report, action record, or terminal transcript. Git-ignore
is not encryption and this repository does not establish or verify a Windows
ACL for these local copies; protect the workstation account and disk.

Generated files:

- `uptime_kuma_admin_password`: login password for Uptime Kuma user `admin`
- `ntfy_admin_password`: login password for ntfy user `admin`
- `ntfy_access_token`: token for regular ntfy user `homeops`, limited to the
  `homeops-alerts` topic
- `backup_key`: separately approval-gated master key for Mission Control
  backup encryption and derived HMAC authentication; never pass it on a command
  line or commit it

The server additionally retains `ntfy_admin_password_hash` and
`ntfy_service_password_hash`. The two hashes and service token are mounted
read-only into ntfy. The randomly generated service plaintext exists only in
the generator-to-hasher stdin pipeline. All persistent server files are mode
`0600` under a mode `0700` directory.
