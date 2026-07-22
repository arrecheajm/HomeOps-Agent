# Mission Control backup destination

This directory is the first independent destination for encrypted Mission
Control volume backups. Git tracks only this explanation; backup archives,
authentication sidecars, and temporary recovery artifacts are ignored.

Do not place plaintext exports here. `backup_mission_control_stack` writes only
authenticated encrypted `current` and `previous` pairs here after verifying the
incoming HMAC. The destructive restore action and drill described in
`docs/mission-control-backup-restore.md` must still be implemented and pass
before Mission Control stores retained household state.
