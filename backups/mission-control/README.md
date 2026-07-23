# Mission Control backup destination

This directory is the first independent destination for encrypted Mission
Control volume backups. Git tracks only this explanation; backup archives,
authentication sidecars, and temporary recovery artifacts are ignored.

Do not place plaintext exports here. `backup_mission_control_stack` writes only
authenticated encrypted `current` and `previous` pairs here after verifying the
incoming HMAC. The bounded destructive restore action described in
`docs/mission-control-backup-restore.md` uses only the `current` pair and does
not write plaintext here. Its separately approved live drill must pass before
Mission Control stores retained household state.
