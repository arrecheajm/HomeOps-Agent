# Architecture

## Summary

HomeOps Agent is a central controller for collecting server health evidence,
preparing approved maintenance workflows, and exploring agentic homelab
operations. It is designed for a small personal fleet where some machines are
access infrastructure and others are intentionally disposable lab boxes.

The controller does not call the OpenAI API. Codex in VS Code provides analysis by reading generated reports and JSON files from this repository.

## Responsibilities

### Controller Machine

The controller runs from the main machine and owns:

- server inventory
- per-server access profiles and rebuildability flags
- SSH connection logic
- approved collection script execution
- JSON parsing and schema validation
- normalization into a fleet health model
- local rule-based issue detection
- HTML report and dashboard generation
- action registry definitions
- approval workflow for supported actions
- history of reports and action attempts

### Managed Servers

Each server exposes small scripts that:

- run locally on that server
- collect health data by default without changing server state
- summarize data before it leaves the server
- output JSON
- perform limited approved actions only when called by the controller

The servers do not run autonomous agents and do not store any OpenAI API key.

### Codex in VS Code

Codex acts as the analyst and operator assistant:

- reads the latest HTML dashboard
- reads matching JSON evidence when more detail is needed
- explains issues and tradeoffs
- recommends predefined action IDs
- asks for approval before risky actions

Codex must not invent direct server maintenance commands when an action registry entry is required.

## Access Model

Inventory entries assign each server one access profile:

- `guarded`: preserve access infrastructure such as VPN.
- `experimental`: allow logged admin work on repairable project boxes.
- `lab`: allow high-power experiments on disposable machines.

The controller validates these profiles at inventory load time. A guarded server
cannot be marked rebuildable.

## Logical Flow

```text
1. Load server inventory and validate access profiles.
2. Validate that each configured remote health command is approved.
3. Connect to each server over SSH.
4. Run approved collection scripts.
5. Capture stdout, stderr, exit code, and timing.
6. Parse JSON output.
7. Validate expected field shapes.
8. Normalize per-server data into one fleet health bundle using inventory identity as the source of truth.
9. Run local rules for common issues using policy thresholds.
10. Write raw data, normalized data, findings, and report artifacts.
11. Supported action execution runs only predefined actions after exact approval.
```

## Recommended Folder Structure

```text
HomeOps-Agent/
  controller/
    __init__.py
    main.py
    config.py
    inventory.py
    ssh_client.py
    collector.py
    normalizer.py
    rules.py
    policy.py
    history.py
    html_report_writer.py
    approvals.py
    action_runner.py
    action_registry.py
    schemas.py

  server-scripts/
    common/
      health_summary.sh
      disk_check.sh
      update_check.sh
      service_check.sh
      security_summary.sh
    docker/
      docker_summary.sh
    openvpn/
      openvpn_status.sh
    ispy/
      ispy_status.sh

  config/
    servers.example.yaml
    policy.yaml

  schemas/
    server_health.schema.json
    fleet_health.schema.json

  docs/
    README.md
    architecture.md
    command-safety.md
    codex-operating-guide.md
    data-schema.md
    implementation-roadmap.md
    server-access-setup.md
    reporting.md
    decision-log.md
    archive/

  reports/
    generated/
      index.html

  history/
    runs/
    actions/

  tests/
    fixtures/
    test_normalizer.py
    test_rules.py
    test_history.py
    test_html_report_writer.py
    test_policy.py
```

## First Implementation Boundary

The current version collects, reports, and supports narrowly scoped approval-gated actions. Risky server-side changes must stay behind predefined action IDs, exact approval, policy checks, and action history.

Inventory identity is authoritative for `server_id` and `role`. If a remote script reports a different identity, the controller preserves it as reported metadata but keeps findings and reports keyed to the inventory entry.
