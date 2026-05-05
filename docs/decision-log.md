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
