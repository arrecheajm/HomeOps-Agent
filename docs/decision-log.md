# Decision Log

## 0001: Controller Does Not Call OpenAI

Status: accepted

Date: 2026-05-05

Decision:

The Python controller will not include OpenAI API integration. Codex in VS Code will provide analysis by reading generated reports and JSON files.

Reasoning:

- The user already intends to run and inspect the project through Codex in VS Code.
- Removing API integration keeps v1 simpler.
- The OpenAI API key is not needed in the repository or controller runtime.
- The controller can stay deterministic and easier to test.

Consequences:

- No `OPENAI_API_KEY` setup is needed.
- No prompt construction or LLM response parsing is needed in controller code.
- Documentation must explain how Codex should operate against generated artifacts.
- Reports and JSON evidence become the controller's main interface to Codex.

## 0002: Managed Servers Run Scripts, Not Agents

Status: accepted

Date: 2026-05-05

Decision:

Managed Ubuntu servers will expose simple scripts for health collection and limited approved actions. They will not run autonomous GPT agents.

Reasoning:

- Keeps server behavior predictable.
- Reduces operational and security risk.
- Avoids distributing API keys.
- Makes debugging easier for a junior-to-mid level engineer.

Consequences:

- Server-side scripts need stable JSON output.
- The controller owns orchestration and policy checks.
- Role-specific scripts can be added incrementally.

## 0003: Executable Actions Must Map to Action IDs

Status: accepted

Date: 2026-05-05

Decision:

Any server-side state change must map to a predefined controller action ID and pass policy checks.

Reasoning:

- Prevents arbitrary command execution.
- Keeps review and approval understandable.
- Creates a clear audit trail.

Consequences:

- Codex may recommend action IDs, not free-form shell commands.
- New actions require explicit implementation and documentation.
- Risky actions require human approval.

## 0004: Server Script Installation Is Explicit

Status: accepted

Date: 2026-05-05

Decision:

The controller will not silently install or replace scripts on managed servers. The first implementation expects scripts to be installed deliberately before real collection runs.

Reasoning:

- Copying files to servers is a server mutation, even when the files are read-only health scripts.
- Explicit installation keeps the first live connection safer and easier to understand.
- Future deployment support can be added as a predefined approval-required action.

Consequences:

- `python -m controller.main collect` expects `remote_health_command` to already exist.
- `collect --dry-run` should be used before a real connection.
- A future deployment command must copy only known repository scripts and require approval before writing to a server.

## 0005: HTML Dashboard Is Generated From Structured Run History

Status: accepted

Date: 2026-05-06

Decision:

The HTML dashboard will be generated from `history/runs/<timestamp>/fleet-health.json`, not from Markdown reports.

Reasoning:

- Fleet JSON contains normalized server IDs, roles, counts, findings, and collection errors.
- Legacy Markdown reports may exist without matching structured run data.
- Grouping by today, this week, earlier this month, and monthly archives is more useful than a flat report list.

Consequences:

- `reports/generated/index.html` is regenerated locally and ignored by git.
- Markdown-only legacy reports are not included in dashboard trends.
- New report visualizations should read structured run history first.

## 0006: Generated Reports Are HTML Only

Status: accepted

Date: 2026-05-09

Decision:

The controller will no longer generate Markdown report files. Generated reports are HTML-only, currently centered on `reports/generated/index.html`.

Reasoning:

- One report surface avoids duplicated content and stale report paths.
- The HTML dashboard already includes current state, trends, and action history.
- Fleet JSON and action JSON remain the structured source of truth for automation and review.

Consequences:

- `python -m controller.main collect` refreshes the HTML dashboard and does not write `homeops-report-<timestamp>.md`.
- `python -m controller.main report` writes an HTML report view.
- Existing generated Markdown files are legacy artifacts and should not be linked or regenerated.

## 0007: Server Authority Is Profile-Based

Status: accepted

Date: 2026-05-12

Decision:

The fleet will be managed as a personal homelab agent environment with
per-server access profiles: `guarded`, `experimental`, and `lab`. Inventory also
tracks whether a server is rebuildable.

Reasoning:

- The servers are not mission-critical production infrastructure.
- The user wants agentic exploration, diagnosis, repair, and potential rebuilds.
- VPN access should remain protected even if other servers are disposable.
- Explicit profiles make broad agent power intentional instead of accidental.

Consequences:

- `openvpn-server` is guarded and not rebuildable.
- `ispy-server` is experimental and rebuildable.
- `container-host` is the Codex lab, lab-profile, and rebuildable.
- Arbitrary admin-command support must check access profile.
- Rebuild workflows require a before-state report and explicit destructive
  approval.

## 0008: Logged Admin Commands Are Profile-Gated

Status: accepted

Date: 2026-05-12

Decision:

The controller may run one free-form root shell command through the
`run_admin_command` action, but only on `experimental` and `lab` access
profiles. The action requires a command, a human-readable intent, exact
approval text, policy checks, and an action history record.

Reasoning:

- The project goal is agentic exploration on disposable or repairable servers.
- `openvpn-server` remains access infrastructure and must not accept arbitrary
  admin shell commands.
- Logging command intent, stdout, stderr, exit code, approval source, and access
  profile makes experiments auditable.

Consequences:

- `ispy-server` and `container-host` can be used for broader investigation after
  dry-run review and exact approval.
- The experimental sudoers profile intentionally grants root shell access for
  the controller action.
- Destructive rebuild workflows still need a before-state report and separate
  destructive approval.

## 0009: Rebuild Planning Starts With Before-State Evidence

Status: accepted

Date: 2026-05-12

Decision:

Before destructive rebuild planning for any `rebuildable` server, the
controller should capture a `before-state` JSON snapshot from the latest fleet
evidence.

Reasoning:

- Rebuildable servers are intentionally disposable, but their current setup can
  still contain useful configuration or troubleshooting evidence.
- A stable snapshot gives Codex and the user a shared reference before proposing
  wipe, reinstall, or overhaul steps.
- The snapshot is local generated history, so it does not require another server
  mutation.

Consequences:

- `before-state` is blocked for servers not marked rebuildable.
- Rebuild planning can refer to a concrete source run, findings, recent actions,
  and captured server state.
- Destructive execution still needs a separate rebuild workflow and approval.

## 0010: Rebuild Plans Are Non-Destructive Drafts

Status: accepted

Date: 2026-05-12

Decision:

The controller can generate `rebuild-plan` JSON artifacts from before-state
snapshots, but the plan command does not execute destructive server actions.

Reasoning:

- The user wants freedom to overhaul disposable servers while keeping the
  process legible and logged.
- A draft plan is the right boundary before wipe/reinstall authority exists.
- Rebuild execution needs a narrower, separate approval model than general
  admin commands.

Consequences:

- Plans are ignored generated history under `history/rebuild-plans/`.
- Plans include preservation targets, phases, verification steps, blocked
  reasons, and a future destructive approval phrase.
- `run_admin_command` remains blocked from destructive disk/rebuild patterns on
  `experimental` servers.

## 0011: Container Host Is The Full-Sudo Codex Lab

Status: accepted

Date: 2026-05-12

Decision:

`container-host` is the Codex lab machine. The controller may run arbitrary
logged sudo commands there through `run_admin_command` after exact approval,
including package installs and destructive commands.

Reasoning:

- The container machine is disposable and exists primarily for agentic
  experimentation.
- The user explicitly wants Codex to have broader power on this box than on the
  VPN or camera machines.
- Keeping the full-power surface isolated to the `lab` profile preserves a clear
  boundary around the access server and intermediate camera server.

Consequences:

- `openvpn-server` remains guarded and does not accept `run_admin_command`.
- `ispy-server` remains intermediate: logged admin commands are available, but
  destructive policy patterns stay blocked.
- `container-host` bypasses forbidden command pattern checks for
  `run_admin_command`, while still requiring exact approval and action history.
