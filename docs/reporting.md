# Reporting

HomeOps writes two report formats from the same run history:

- Markdown snapshots for detailed reading.
- An HTML dashboard for scanning current status and recent trends.

## Source Of Truth

Structured reporting uses:

```text
history/runs/<timestamp>/fleet-health.json
history/actions/<timestamp>-<server_id>-<action_id>.json
```

Markdown-only reports without a matching `fleet-health.json` are legacy artifacts and are not included in the HTML dashboard timeline.

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
- historical charts for findings, pending updates, reboot-required state, and Docker issues
- grouped run timeline
- links to Markdown reports, fleet JSON, and action record JSON

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
than parsing Markdown reports.

## Action History

Every action dry-run, denied approval, completed action, or failed action writes
a JSON record under:

```text
history/actions/
```

The dashboard and Markdown reports load these records and show the most recent
action attempts with server ID, action ID, status, dry-run state, and arguments.
This keeps mutating operations auditable even after the controller grows beyond
read-only collection.

## Report Files

Per-run Markdown reports use:

```text
reports/generated/homeops-report-<timestamp>.md
```

The dashboard links to a Markdown report when one exists for the run.
