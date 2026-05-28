# Active Work

Purpose: this is the daily Codex handoff. Read this first before inspecting
broader docs, history, generated reports, or source files.

Last updated: 2026-05-28.

## Session Start

Use this prompt for normal project sessions:

```text
Quick resume. Read ACTIVE_WORK.md and reports/generated/codex-brief.md only,
then continue the next step. Keep output concise and do not run a full fleet
review unless I ask for it.
```

Refresh the generated brief when report pointers may be stale:

```powershell
python -m controller.main codex-brief
```

## Thinking Level Guidance

- Start at `medium` for daily quick resume, status-only work, doc cleanup, and
  narrow edits with clear acceptance criteria.
- Use `high` for normal implementation, test failures, CLI behavior changes,
  and cross-file code changes after the scope is known.
- Use `extra high` only for approval-gated server mutation design, rebuild
  execution design, security boundaries, architecture changes, or confusing
  failures where the cheaper pass did not explain the issue.

Default daily pattern: begin at `medium`, then raise to `high` only when the
next concrete implementation task needs it.

## Current Project Focus

Primary operating model: HomeOps Agent is a deterministic local controller.
Codex reads local evidence and recommends next steps. Managed servers run
approved scripts and predefined action IDs, not autonomous agents.

Quick-resume workflow status:

- Implemented `ACTIVE_WORK.md` as the single daily handoff source.
- Implemented `python -m controller.main codex-brief`.
- Archived `docs/active-operations-plan.md` to `docs/archive/`.
- Updated README, docs index, Codex guide, roadmap, tracker, and maintenance
  runbook to point daily sessions here.
- Added focused tests for the brief generator and CLI parser wiring.
- Verified with `python -m unittest tests.test_codex_brief` and
  `python -m unittest discover -s tests`.

Current implementation focus after this handoff work:

- Design an approval-gated rebuild execution workflow for rebuildable servers.
- Keep that workflow separate from `run_admin_command`.
- Preserve the guarded `openvpn-server` boundary.
- Use before-state snapshots and non-destructive rebuild plans before any
  destructive execution design.

## Current Resume State

- Check `git status --short --branch` at session start for branch cleanliness.
- Latest fleet report run: `2026-05-28T14-49-34Z`.
- Latest fleet report status: 0 critical, 3 warnings, 1 info.
- `openvpn-server` is reachable again and has 1 security update pending.
- `ispy-server` has 22 security updates pending and failed legacy `ispy`
  service while `AgentDVR` remains active in the collected service list.
- `container-host` has 1 package update pending and Docker is active with no
  unhealthy containers.
- `ACTIVE_WORK.md` is the single daily handoff source.
- `reports/generated/codex-brief.md` is the compact generated startup brief.
- `docs/active-operations-plan.md` was archived because it duplicated daily
  current-state and next-step guidance.
- `IMPLEMENTATION_TRACKER.md` remains the durable implementation state record.
- `docs/implementation-roadmap.md` remains the phase roadmap, not the daily
  resume source.

## Immediate Next Steps

1. Review the uncommitted quick-resume workflow diff if needed.
2. Commit the quick-resume workflow once the user is satisfied with the handoff.
3. Start the explicit rebuild execution design for rebuildable servers.
4. Keep rebuild execution separate from `run_admin_command` and require
   before-state evidence plus exact destructive approval.

## Relevant Files

- `ACTIVE_WORK.md`: daily handoff and thinking-level guidance.
- `reports/generated/codex-brief.md`: generated compact session brief.
- `docs/codex-operating-guide.md`: Codex operating rules.
- `IMPLEMENTATION_TRACKER.md`: durable implementation status and checklist.
- `docs/implementation-roadmap.md`: long-range phase roadmap.
- `docs/archive/active-operations-plan.md`: archived current-state plan.

## Useful Commands

```powershell
python -m controller.main codex-brief
python -m controller.main collect
python -m controller.main dashboard
python -m controller.main catalog
python -m controller.main check --input history\runs\<latest-run>\fleet-health.json
python -m unittest discover -s tests
```

## Avoid By Default

- Do not start each session with a full project review.
- Do not read archived docs unless active docs are missing context.
- Do not run live fleet collection unless current server state is needed.
- Do not execute approval-required actions without exact user approval.
