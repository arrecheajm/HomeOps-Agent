# Implementation Roadmap

## Current Status

The controller can generate Markdown reports and an HTML dashboard, load inventory with optional SSH identity files, validate approved remote health commands, dry-run collection, validate collected server health shapes, normalize inventory identity, and run collector logic under tests.

The first real read-only collection has succeeded for all three servers: `openvpn-server`, `ispy-server`, and `container-host`. `container-host` is online at `192.168.86.58`, local inventory uses `containerserver@192.168.86.58`, SSH key authentication works, and the approved read-only health script is installed.

The next milestone is reviewing the current findings, especially the restarting `watchtower` container on `container-host`, and using the new approval-gated action runner only after explicit approval.

## Phase 1: Documentation and Project Shape

Goal: lock the operating model before writing controller code.

- document architecture
- document safety rules
- document Codex operating expectations
- define initial JSON data shape
- create implementation tracker

## Phase 2: Controller Skeleton

Goal: make the CLI runnable locally without touching real servers.

- create `controller/main.py`
- create command parsing
- create config loading
- create fixture-based report generation
- write an example report to `reports/generated/`

Target command:

```bash
python -m controller.main report --fixture tests/fixtures/fleet-health.json
```

## Phase 3: Server Inventory and SSH Collection

Goal: collect read-only health JSON from configured servers.

- add `config/servers.example.yaml`
- add inventory loader
- add SSH client wrapper with timeout handling
- support optional identity files for dedicated controller SSH keys
- reject unapproved remote health commands
- run one approved collection command per server
- save raw collection results under `history/runs/`

Target command:

```bash
python -m controller.main collect
```

## Phase 4: Server Scripts

Goal: produce compact JSON from Ubuntu hosts.

- add `server-scripts/common/health_summary.sh`
- add disk summary
- add update summary
- add service summary
- add security summary
- add role-specific scripts for Docker, OpenVPN, and iSpy

## Phase 5: Normalization and Local Rules

Goal: detect common issues without Codex.

- validate server JSON
- normalize into fleet health JSON
- keep inventory `server_id` and `role` authoritative
- load rule thresholds from `config/policy.yaml`
- detect failed services
- detect high disk usage
- detect pending security updates
- detect reboot-required status
- detect unhealthy Docker containers
- detect suspicious SSH login spikes

## Phase 6: Markdown Reports

Goal: generate readable evidence for humans and Codex.

- add report writer
- include fleet summary table
- include findings by severity
- include per-server details
- include recommended action IDs
- include actions taken from history

## Phase 6b: HTML Dashboard

Goal: make run history easier to scan visually.

- load structured run history from `history/runs/`
- group runs by today, this week, earlier this month, and monthly archive
- render latest server status cards
- render latest findings by severity
- render historical charts from structured run JSON
- link dashboard entries to Markdown reports and fleet JSON
- refresh dashboard after collection

## Phase 7: Action Registry and Approval Flow

Goal: allow safe, predefined maintenance actions.

- create action registry
- implement `actions list`
- implement dry-run behavior
- implement approval prompt
- write action history
- keep destructive or config-changing operations out of scope

Status: in progress. The registry exists, `actions list` works, and
`restart_docker_container` has dry-run, exact approval, execution, and action
history support. Other approval-required actions remain unimplemented.

## Phase 8: Hardening

Goal: make failures understandable and safe.

- add tests for config, rules, reports, and policy
- add tests for command allowlisting, identity normalization, and schema failures
- redact sensitive values
- improve SSH error reporting
- handle partial fleet failures
- document server setup
- document adding a new check
- document adding a new action

## Minimum Viable Version

The read-only MVP is complete for enabled servers when this works:

```bash
python -m controller.main collect
python -m controller.main report
```

And produces:

```text
history/runs/<timestamp>/fleet-health.json
reports/generated/homeops-report-<timestamp>.md
reports/generated/index.html
```

MVP constraints:

- read-only collection only
- no OpenAI API integration
- no automated risky actions
- local rule findings included in report
- report and dashboard clear enough for Codex to analyze from VS Code
