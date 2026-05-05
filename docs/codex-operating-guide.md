# Codex Operating Guide

This repository is intended to be opened and operated from VS Code with Codex.

Codex is the analyst. The controller is the deterministic evidence collector and approved action runner.

## When Reviewing Server Health

1. Read the latest generated Markdown report in `reports/generated/`.
2. If more detail is needed, read the matching run directory in `history/runs/`.
3. Use local JSON evidence as the source of truth.
4. Explain findings by severity and operational impact.
5. Recommend only predefined action IDs when an executable action is appropriate.
6. Ask for explicit approval before running any `approval_required` action.

## What Codex Must Not Do

- Do not run arbitrary maintenance commands directly against home servers.
- Do not invent one-off SSH commands to mutate server state.
- Do not delete files or prune storage without explicit approval.
- Do not change firewall, SSH, OpenVPN, Docker, or system configuration without explicit approval.
- Do not reboot a server without explicit approval.
- Do not add OpenAI API integration to the controller unless the project direction changes.
- Do not install or replace server scripts unless the user explicitly approves that deployment step.

## Normal Operating Pattern

```text
1. Run collection/report command.
2. Inspect generated artifacts.
3. Summarize issues.
4. Map any recommendation to an action_id.
5. Ask the user for approval when required.
6. Run the controller action command only after approval.
7. Re-run collection to verify results.
```

## Preferred Findings Format

When explaining a report, use this order:

```text
Critical findings
Warnings
Informational notes
Recommended next actions
Actions requiring approval
Residual risk or missing data
```

## Source Priority

Prefer evidence in this order:

1. Generated fleet health JSON
2. Generated Markdown report
3. Controller action history
4. Server script source
5. Direct read-only inspection commands

Direct server mutation commands are not part of normal operation.
