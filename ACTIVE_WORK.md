# Active Work

Purpose: this is the daily Codex handoff. Read this first before inspecting
broader docs, history, generated reports, or source files.

Last updated: 2026-07-18.

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

Current implementation focus:

- Plan and implement the LAN-only `container-host` House OS described in
  `docs/container-host-house-os-plan.md`.
- Keep `openvpn-server` guarded and avoid VPN-impacting work unless explicitly
  requested.
- Keep the currently healthy `ispy-server` camera workload isolated from the
  new household services.
- Extend HomeOps with repeatable desired-state stack, storage, backup, restore,
  upgrade, and rollback workflows before treating new application data as
  durable.

Recommended thinking level for the next work:

- Start at `medium` for container inventory, plan refinement, report review,
  and read-only storage planning.
- Use `high` for desired-state schema, controller lifecycle actions, Compose
  bundles, backup/restore logic, and cross-file implementation.
- Use `extra high` only before approval-required cleanup, storage formatting,
  firewall or routing changes, destructive stack removal, or rebuild execution.

## Current Resume State

- Check `git status --short --branch` at session start for branch cleanliness.
- Latest fleet report run: `2026-07-18T18-47-49Z`; all 3 servers collected
  without errors.
- Latest fleet status: 0 critical, 0 warning, and 1 informational finding.
- `openvpn-server` has 2 non-security package updates pending; no reboot is
  required.
- `ispy-server` is current and AgentDVR is active with no fleet finding.
- `container-host` is current with Docker active, 9 of 9 containers running,
  and no unhealthy containers or host finding.
- `container-host` has an i5-4210U with 4 CPU threads, about 8 GB RAM, and about
  80 GB free on the root disk. Current load and memory use are low.
- The accepted direction is a LAN-only House OS combining Home Assistant,
  Mealie, Paperless-ngx, Forgejo, and a household Mission Control dashboard.
- A 1 TB USB drive can be added for larger application data and exports. Keep
  databases and latency-sensitive state on the internal disk.
- A phone on normal home Wi-Fi must be able to scan a PDF and upload it through
  the Paperless web dashboard.
- Existing containers may be removed if sanitized inventory shows they are not
  useful.
- Exact Wi-Fi switch/garage brands, phone platform, USB enclosure, and second
  backup destination remain open inputs.
- Durable plan: `docs/container-host-house-os-plan.md`.
- `ACTIVE_WORK.md` is the single daily handoff source.
- `reports/generated/codex-brief.md` is the compact generated startup brief.
- `docs/active-operations-plan.md` was archived because it duplicated daily
  current-state and next-step guidance.
- `IMPLEMENTATION_TRACKER.md` remains the durable implementation state record.
- `docs/implementation-roadmap.md` remains the phase roadmap, not the daily
  resume source.

## Immediate Next Steps

1. Add sanitized Docker inventory and classify all 9 current containers as
   keep, replace, or remove.
2. Record the smart-switch and garage-controller brands/apps, phone platform,
   USB drive details, and independent backup destination.
3. Define `config/workloads.yaml`, version-controlled Compose bundles, and
   approval-gated stack lifecycle operations.
4. Implement USB mount/sentinel preflight before storage-dependent deployment.
5. Deploy in stages: Mission Control, Home Assistant, Mealie, Paperless-ngx,
   then Forgejo and an optional limited CI runner.
6. Prove reboot persistence and backup/restore for each stateful application
   before expanding its use.

## Relevant Files

- `ACTIVE_WORK.md`: daily handoff and thinking-level guidance.
- `docs/container-host-house-os-plan.md`: accepted container-host application,
  storage, safety, and HomeOps delivery direction.
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
python -m controller.main container-review --server container-host
python -m controller.main check --input history\runs\<latest-run>\fleet-health.json
python -m unittest discover -s tests
```

## Avoid By Default

- Do not start each session with a full project review.
- Do not read archived docs unless active docs are missing context.
- Do not run live fleet collection unless current server state is needed.
- Do not execute approval-required actions without exact user approval.
