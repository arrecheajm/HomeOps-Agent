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

Current implementation focus:

- Improve `ispy-server` health and AgentDVR reliability.
- Keep `openvpn-server` guarded and avoid VPN-impacting work unless explicitly
  requested.
- Keep `container-host` as the lab box; it is currently in acceptable shape.
- Defer approval-gated rebuild execution design until the iSpy reliability pass
  is complete.

Recommended thinking level for the next work:

- Start at `medium` for focused collection, before-state capture, report review,
  and read-only inspection planning.
- Use `high` for implementation work that changes controller checks, server
  scripts, AgentDVR monitoring, or configuration recommendations.
- Use `extra high` only before live approval-required mutations on
  `ispy-server`, destructive cleanup, rebuild execution design, or changes that
  could affect camera recording availability.

## Current Resume State

- Check `git status --short --branch` at session start for branch cleanliness.
- Latest fleet report run: `2026-05-28T14-49-34Z`.
- Latest focused `ispy-server` run: `2026-05-28T15-03-53Z`.
- Latest focused `ispy-server` status: 0 critical, 2 warnings, 0 info.
- `openvpn-server` is reachable again and has 1 security update pending.
- `ispy-server` has 22 security updates pending and failed legacy `ispy`
  service while `AgentDVR` remains active in the collected service list.
- Captured before-state snapshot:
  `history/before-state/2026-05-28T15-04-03Z-ispy-server.json`.
- Dry-ran `apply_security_updates` for `ispy-server`; approval phrase is
  `Approve action apply_security_updates on ispy-server`.
- Read-only service inspection found `AgentDVR.service` active with
  `Restart=always`, running `/home/spy/AgentDVR/Agent` as user `spy`.
- Read-only service inspection found failed `ispy.service` is a duplicate stale
  unit running `/home/spy/AgentDVR/start_agent.sh`; that script only calls
  `./Agent`, so it fails under systemd because the unit lacks the AgentDVR
  working directory.
- AgentDVR media/config files are active today under `/home/spy/AgentDVR/Media`;
  media usage is small at about 46 MB, so current evidence does not suggest
  disk pressure.
- Implemented and generated focused iSpy tracking report:
  `reports/generated/ispy-review.html` and `reports/generated/ispy-review.json`.
- `ispy-review` currently tracks findings, before-state, recent actions,
  AgentDVR service diagnosis, failed legacy service diagnosis, reliability
  checklist gaps, and recommended dry-run commands.
- Read-only AgentDVR XML/DB inspection found 2 configured cameras and 2
  microphones. Both cameras have source URI configuration present, and the
  current manual evidence includes sanitized endpoint reachability checks.
- AgentDVR recording DB has 50 file records and 100 alert records. Recording
  evidence exists for Camera 5 only, newest file `2026-05-28T17:25:42Z`;
  Camera 4 has no recording DB evidence in the sanitized inspection.
- Recent AgentDVR logs show Camera 4 repeatedly fails before recording with
  FFmpeg `OPEN_INPUT: Connection refused` and reconnect attempts. Recent log
  sample counted 90 errors and 45 exceptions for Camera 4.
- Recent AgentDVR logs show Camera 5 opening and closing recordings. Recent DB
  and log evidence confirms Camera 5 is recording.
- Read-only RTSP reachability from `ispy-server` confirms Camera 4's configured
  endpoint host ending `.166` refuses TCP connections on port 554, while Camera
  5's configured endpoint host ending `.164` accepts RTSP and returns
  `RTSP/1.0 200 OK`.
- `ispy-review` now surfaces sanitized per-camera endpoint checks without
  storing credentials or full stream URLs in the report.
- Configured camera media directories `KDWDF` and `BENRC` were not present
  under `/home/spy/AgentDVR/Media`, so storage path intent needs verification.
- `ispy-review` now reads sanitized AgentDVR evidence from
  `reports/generated/ispy-agentdvr-evidence.json` when present.
- Stopping point: iSpy report implementation and endpoint evidence are ready to
  commit. Full tests passed with `python -m unittest discover -s tests`.
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

1. Review whether to approve `apply_security_updates` on `ispy-server`.
2. Plan a cleanup action for stale `ispy.service`: likely disable the duplicate
   unit and reset failed state, after explicit approval.
3. Use `reports/generated/ispy-review.html` as the working report for the iSpy
   reliability pass.
4. Troubleshoot Camera 4 stream reachability/config because AgentDVR reports
   `OPEN_INPUT: Connection refused` and direct RTSP TCP from `ispy-server` is
   refused. Next read-only checks should confirm whether Camera 4 is powered,
   has changed IP/RTSP port, or uses a different RTSP path than the configured
   endpoint.
5. Determine whether Camera 4/5 media directories should exist under the
   default media path or whether AgentDVR is storing recordings elsewhere.
6. Promote the current manual AgentDVR evidence gathering into a durable
   read-only collection command so camera recording and endpoint status can be
   regenerated without ad hoc SSH inspection.

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
python -m controller.main ispy-review --server ispy-server
python -m controller.main check --input history\runs\<latest-run>\fleet-health.json
python -m unittest discover -s tests
```

## Avoid By Default

- Do not start each session with a full project review.
- Do not read archived docs unless active docs are missing context.
- Do not run live fleet collection unless current server state is needed.
- Do not execute approval-required actions without exact user approval.
