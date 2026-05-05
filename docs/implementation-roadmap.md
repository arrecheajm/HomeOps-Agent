# Implementation Roadmap

## Current Status

The controller can now generate fixture reports, load the example inventory, build SSH commands, dry-run collection, and run collector logic under tests. No real server collection has been run yet.

The next milestone is preparing the servers with the read-only health script and creating a local `config/servers.yaml`.

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

## Phase 7: Action Registry and Approval Flow

Goal: allow safe, predefined maintenance actions.

- create action registry
- implement `actions list`
- implement dry-run behavior
- implement approval prompt
- write action history
- keep destructive or config-changing operations out of scope

## Phase 8: Hardening

Goal: make failures understandable and safe.

- add tests for config, rules, reports, and policy
- redact sensitive values
- improve SSH error reporting
- handle partial fleet failures
- document server setup
- document adding a new check
- document adding a new action

## Minimum Viable Version

The MVP is complete when this works:

```bash
python -m controller.main collect
python -m controller.main report
```

And produces:

```text
history/runs/<timestamp>/fleet-health.json
reports/generated/homeops-report-<timestamp>.md
```

MVP constraints:

- read-only collection only
- no OpenAI API integration
- no automated risky actions
- local rule findings included in report
- report clear enough for Codex to analyze from VS Code
