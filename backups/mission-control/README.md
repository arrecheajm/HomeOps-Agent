# Mission Control backup destination

This directory is the first independent destination for encrypted Mission
Control volume backups. Git tracks only this explanation; backup archives,
authentication sidecars, and temporary recovery artifacts are ignored.

Do not place plaintext exports here. The backup action and destructive restore
drill described in `docs/mission-control-backup-restore.md` must be implemented
and pass before Mission Control stores retained household state.
