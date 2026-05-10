# Reporting

HomeOps writes generated HTML report surfaces from structured history:

- An HTML dashboard for current status, action history, and recent trends.
- An HTML fleet catalog for server capabilities and workload placement guidance.

## Source Of Truth

Structured reporting uses:

```text
history/runs/<timestamp>/fleet-health.json
history/actions/<timestamp>-<server_id>-<action_id>.json
knowledge/fleet-catalog.json
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

## Fleet Catalog

The fleet catalog keeps basic server knowledge in a tracked JSON file and renders
a separate HTML report:

```text
knowledge/fleet-catalog.json
reports/generated/fleet-catalog.html
```

Generate or refresh the catalog:

```bash
python -m controller.main catalog
```

Normal collection and dashboard generation also refresh the catalog from the
latest run. The catalog captures:

- server role, hostname, OS, kernel, hardware details, CPU thread count, load, memory use, uptime, and root disk free space
- role-specific services
- Docker capability and running container counts
- maintenance state
- inferred capabilities, constraints, and placement guidance

The tracked JSON is the durable repo knowledge. The HTML file is generated and
ignored by git like the dashboard.

If hardware fields show as `unknown`, deploy the latest approved health script
with `deploy_health_script`, then run collection and regenerate the catalog.

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
reports/generated/fleet-catalog.html
```

The controller no longer writes `homeops-report-<timestamp>.md` files.
