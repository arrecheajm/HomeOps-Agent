# Codex Operating Guide

This repository is intended to be opened and operated from VS Code with Codex.

Codex is the analyst. The controller is the deterministic evidence collector. A narrow approval-gated action runner exists for supported actions.

## When Reviewing Server Health

1. Read the latest generated HTML dashboard at `reports/generated/index.html`.
2. If more detail is needed, read the matching run directory in `history/runs/`.
3. Use normalized fleet JSON as the source of truth for server IDs and roles.
4. Explain findings by severity and operational impact.
5. Recommend only predefined action IDs when an executable action is appropriate.
6. Do not run mutating actions unless the user gives exact approval for a supported action.

## Fleet Review Shortcut

When the user says `run fleet review`, perform the safe review loop:

1. Check the worktree with `git status --short --branch`.
2. Run `python -m controller.main collect`.
3. Run `python -m controller.main dashboard`.
4. Run `python -m controller.main catalog`.
5. Identify the latest directory under `history/runs/`.
6. Run `python -m controller.main check --input history\runs\<latest-run>\fleet-health.json`.
7. Summarize current findings and recommended next steps.

Do not execute approval-required actions during fleet review. Recommend dry-run
commands only, then wait for exact approval before any live action execution.

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
1. Run collection or dashboard command.
2. Inspect generated HTML and JSON artifacts.
3. Summarize issues.
4. Map any recommendation to an action_id.
5. Run action dry-runs first when an implemented action may apply.
6. Ask the user for exact approval before any server mutation.
7. Re-run collection to verify results after approved maintenance.
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
2. Generated HTML dashboard
3. Server script source
4. Direct read-only inspection commands approved by the user

Direct server mutation commands are not part of normal operation. Use controller
action IDs and action history for supported mutations.
