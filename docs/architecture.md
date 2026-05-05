# Architecture

## Summary

HomeOps Agent is a central controller for collecting server health evidence and running approved maintenance actions. It is designed for a small home fleet and for a developer who wants the system to stay transparent while learning infrastructure automation.

The controller does not call the OpenAI API. Codex in VS Code provides analysis by reading generated reports and JSON files from this repository.

## Responsibilities

### Controller Machine

The controller runs from the main machine and owns:

- server inventory
- SSH connection logic
- script execution
- JSON parsing and schema validation
- normalization into a fleet health model
- local rule-based issue detection
- Markdown report generation
- action registry enforcement
- approval workflow
- history of reports and actions

### Managed Servers

Each server exposes small scripts that:

- run locally on that server
- collect read-only health data by default
- summarize data before it leaves the server
- output JSON
- perform limited approved actions only when called by the controller

The servers do not run autonomous agents and do not store any OpenAI API key.

### Codex in VS Code

Codex acts as the analyst and operator assistant:

- reads the latest Markdown report
- reads matching JSON evidence when more detail is needed
- explains issues and tradeoffs
- recommends predefined action IDs
- asks for approval before risky actions

Codex must not invent direct server maintenance commands when an action registry entry is required.

## Logical Flow

```text
1. Load server inventory.
2. Connect to each server over SSH.
3. Run approved read-only collection scripts.
4. Capture stdout, stderr, exit code, and timing.
5. Parse JSON output.
6. Validate against the expected schema.
7. Normalize per-server data into one fleet health bundle.
8. Run local rules for common issues.
9. Write raw data, normalized data, findings, and report artifacts.
10. Optionally run a predefined action after approval.
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
    report_writer.py
    approvals.py
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
    architecture.md
    command-safety.md
    codex-operating-guide.md
    data-schema.md
    implementation-roadmap.md
    decision-log.md

  reports/
    EXAMPLE_REPORT.md
    generated/

  history/
    runs/
    actions/

  tests/
    fixtures/
    test_normalizer.py
    test_rules.py
    test_policy.py
```

## First Implementation Boundary

The first version should collect and report only. Risky server-side changes should not be implemented until collection, validation, reports, and local rule checks are working.
