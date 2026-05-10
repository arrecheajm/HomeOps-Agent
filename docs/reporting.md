# Reporting

HomeOps writes one generated report surface from run history:

- An HTML dashboard for current status, action history, and recent trends.

## Source Of Truth

Structured reporting uses:

```text
history/runs/<timestamp>/fleet-health.json
history/actions/<timestamp>-<server_id>-<action_id>.json
```

Legacy Markdown reports are not generated anymore and are not included in the HTML dashboard timeline.

## HTML Dashboard

Generate or refresh the dashboard:

```bash
python -m controller.main dashboard
```

Normal collection also refreshes it automatically:

```bash
python -m controller.main collect
```

Dashboard output:

```text
reports/generated/index.html
```

Open that file in a browser to review:

- latest run summary
- server status cards
- latest findings by severity
- recent action attempts from action history
- agent/action history metrics, status chart, and action timeline
- historical charts for findings, pending updates, reboot-required state, and Docker issues
- grouped run timeline
- links to fleet JSON and action record JSON

`reports/generated/` is ignored by git. Regenerate the dashboard locally whenever needed instead of committing generated HTML.

## Run Grouping

The dashboard groups run history into operating periods:

- latest run as the primary status
- today
- this week
- earlier this month
- older monthly archives

Runs are sorted newest first inside each group.

## Historical Charts

The dashboard renders historical charts directly from structured run JSON:

- finding severity counts over recent runs
- pending package updates by server
- reboot-required server counts
- Docker issue counts

Charts intentionally use `history/runs/<timestamp>/fleet-health.json` rather
than parsing legacy Markdown reports.

## Action History

Every action dry-run, denied approval, completed action, or failed action writes
a JSON record under:

```text
history/actions/
```

The dashboard loads these records and shows the most recent action attempts with
server ID, action ID, status, dry-run state, and arguments.
This keeps mutating operations auditable even after the controller grows beyond
read-only collection.

The `Agent History` dashboard view renders the same records as historical data:

- total action attempts
- dry-run, completed, denied, and failed counts
- action outcome chart by day
- action timeline with risk, approval source, arguments, exit code, and JSON link

Running `python -m controller.main actions run ...` refreshes the HTML dashboard
after the action record is written, including dry-runs and denied attempts.

## Report Files

The generated HTML report is:

```text
reports/generated/index.html
```

The controller no longer writes `homeops-report-<timestamp>.md` files.
