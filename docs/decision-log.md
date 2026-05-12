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
- `container-host` is lab-profile and rebuildable.
- Future arbitrary admin-command support must check access profile.
- Rebuild workflows require a before-state report and explicit destructive
  approval.
