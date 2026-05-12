"""Command line entrypoint for HomeOps controller."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import (
    action_registry,
    action_runner,
    approvals,
    collector,
    config,
    history,
    inventory,
    policy,
    rules,
)
from .fleet_catalog import write_fleet_catalog
from .html_report_writer import write_dashboard
from .ssh_client import build_ssh_command


def refresh_html_reports(
    runs_dir: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Refresh all generated HTML report surfaces from run and action history."""

    actual_output_dir = output_dir or config.GENERATED_REPORTS_DIR
    runs = history.discover_run_summaries(runs_dir)
    dashboard_path = write_dashboard(
        runs,
        actual_output_dir,
        history.discover_action_summaries(),
    )
    refreshed: dict[str, Any] = {
        "dashboard_path": dashboard_path,
        "runs": runs,
        "run_count": len(runs),
        "catalog_path": None,
        "knowledge_path": None,
    }
    if runs:
        knowledge_path, catalog_path = write_fleet_catalog(runs[0], actual_output_dir)
        refreshed["catalog_path"] = catalog_path
        refreshed["knowledge_path"] = knowledge_path
    return refreshed


def print_report_refresh(refreshed: dict[str, Any]) -> None:
    """Print refreshed report paths."""

    catalog_path = refreshed.get("catalog_path")
    knowledge_path = refreshed.get("knowledge_path")
    print(f"Wrote HTML dashboard: {refreshed['dashboard_path']}")
    if catalog_path:
        print(f"Wrote fleet catalog: {catalog_path}")
    if knowledge_path:
        print(f"Wrote fleet knowledge: {knowledge_path}")


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise SystemExit(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return data


def apply_local_rules(fleet: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of fleet health with rule findings attached."""

    updated = dict(fleet)
    try:
        policy_data = policy.load_policy()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    updated["findings"] = rules.evaluate_fleet(updated, policy_data)
    updated["servers_checked"] = len(updated.get("servers") or [])
    updated["servers_failed"] = len(updated.get("collection_errors") or [])
    return updated


def resolve_input_path(args: argparse.Namespace) -> Path:
    """Resolve the fleet health input path for report and check commands."""

    if getattr(args, "input", None):
        return Path(args.input)
    if getattr(args, "fixture", None):
        return Path(args.fixture)
    return config.DEFAULT_FIXTURE_PATH


def command_report(args: argparse.Namespace) -> int:
    input_path = resolve_input_path(args)
    fleet = apply_local_rules(load_json(input_path))
    output_dir = Path(args.output_dir) if args.output_dir else config.GENERATED_REPORTS_DIR
    run_summary = history.run_summary_from_fleet(fleet, input_path)
    dashboard_path = write_dashboard(
        [run_summary],
        output_dir,
        history.discover_action_summaries(),
    )

    counts = rules.count_by_severity(fleet.get("findings") or [])
    print(f"Wrote HTML report: {dashboard_path}")
    print(
        "Findings: "
        f"{counts['critical']} critical, "
        f"{counts['warning']} warning, "
        f"{counts['info']} info"
    )
    return 0


def command_check(args: argparse.Namespace) -> int:
    fleet = apply_local_rules(load_json(resolve_input_path(args)))
    findings = fleet.get("findings") or []
    counts = rules.count_by_severity(findings)

    print(
        "Findings: "
        f"{counts['critical']} critical, "
        f"{counts['warning']} warning, "
        f"{counts['info']} info"
    )
    for finding in findings:
        print(
            f"- {finding['severity']}: {finding['server_id']} "
            f"{finding['code']} - {finding['message']}"
        )
    return 1 if counts["critical"] else 0


def command_collect(args: argparse.Namespace) -> int:
    inventory_path = Path(args.inventory) if args.inventory else config.DEFAULT_INVENTORY_PATH

    try:
        servers = inventory.load_inventory(inventory_path)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    if args.dry_run:
        print(f"Inventory: {inventory_path}")
        print(f"Enabled servers: {len(servers)}")
        for server in servers:
            print(f"- {server.server_id}: {' '.join(build_ssh_command(server))}")
        return 0

    fleet, run_dir = collector.collect_fleet(servers)
    fleet = apply_local_rules(fleet)
    fleet_path = collector.save_fleet_health(fleet, run_dir)
    refreshed = refresh_html_reports()

    counts = rules.count_by_severity(fleet.get("findings") or [])
    print(f"Run directory: {run_dir}")
    print(f"Wrote fleet health: {fleet_path}")
    print_report_refresh(refreshed)
    print(
        "Findings: "
        f"{counts['critical']} critical, "
        f"{counts['warning']} warning, "
        f"{counts['info']} info"
    )
    return 1 if fleet.get("collection_errors") else 0


def command_actions_list(_args: argparse.Namespace) -> int:
    print("| Action ID | Risk | Implemented | Description |")
    print("|---|---|---:|---|")
    for action in action_registry.list_actions():
        implemented = "yes" if action.get("implemented") else "no"
        print(
            f"| `{action['action_id']}` | {action['risk']} | "
            f"{implemented} | {action['description']} |"
        )
    return 0


def command_actions_run(args: argparse.Namespace) -> int:
    inventory_path = Path(args.inventory) if args.inventory else config.DEFAULT_INVENTORY_PATH

    try:
        servers = inventory.load_inventory(inventory_path)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    arguments: dict[str, Any] = {}
    if args.container:
        arguments["container"] = args.container
    if args.service:
        arguments["service"] = args.service
    if args.admin_command:
        arguments["command"] = args.admin_command
    if args.intent:
        arguments["intent"] = args.intent

    approval_text = args.approval
    if not args.dry_run and approval_text is None and sys.stdin.isatty():
        expected = approvals.approval_phrase(args.action_id, args.server, arguments)
        print("Approval required. Type this exact phrase to continue:")
        print(expected)
        approval_text = input("> ")

    try:
        attempt = action_runner.run_action(
            args.action_id,
            args.server,
            servers,
            arguments,
            approval_text=approval_text,
            dry_run=args.dry_run,
        )
    except action_runner.ActionError as exc:
        refreshed = refresh_html_reports()
        raise SystemExit(
            f"{exc}\nWrote HTML dashboard: {refreshed['dashboard_path']}"
        ) from exc

    record = attempt.record
    status = record.get("status", "unknown")
    refreshed = refresh_html_reports()
    print(f"Action status: {status}")
    print(f"Action ID: {record['action_id']}")
    print(f"Server: {record['server_id']}")
    commands = record.get("commands")
    if isinstance(commands, list) and len(commands) > 1:
        print("Commands:")
        for index, command in enumerate(commands, start=1):
            if isinstance(command, list):
                print(f"{index}. {' '.join(str(part) for part in command)}")
    else:
        print(f"Command: {' '.join(record['command'])}")
    if args.dry_run:
        print(f"Approval phrase: {record['expected_approval']}")
    else:
        print(f"Exit code: {record.get('exit_code')}")
    print(f"Wrote action record: {attempt.record_path}")
    print_report_refresh(refreshed)
    return 0 if status in {"dry_run", "completed"} else 1


def command_dashboard(args: argparse.Namespace) -> int:
    runs_dir = Path(args.runs_dir) if args.runs_dir else config.RUNS_DIR
    output_dir = Path(args.output_dir) if args.output_dir else config.GENERATED_REPORTS_DIR
    refreshed = refresh_html_reports(runs_dir, output_dir)
    print_report_refresh(refreshed)
    print(f"Runs included: {refreshed['run_count']}")
    return 0


def command_catalog(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir) if args.output_dir else config.GENERATED_REPORTS_DIR
    knowledge_path = (
        Path(args.knowledge_path) if args.knowledge_path else config.FLEET_CATALOG_PATH
    )
    if args.input:
        input_path = Path(args.input)
        fleet = apply_local_rules(load_json(input_path))
        run_summary = history.run_summary_from_fleet(fleet, input_path)
    else:
        runs = history.discover_run_summaries()
        if not runs:
            raise SystemExit("No run history found. Run collection before cataloging.")
        run_summary = runs[0]

    written_knowledge_path, catalog_path = write_fleet_catalog(
        run_summary,
        output_dir,
        knowledge_path,
    )
    print(f"Wrote fleet catalog: {catalog_path}")
    print(f"Wrote fleet knowledge: {written_knowledge_path}")
    print(f"Source run: {run_summary.run_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HomeOps controller")
    subparsers = parser.add_subparsers(dest="command", required=True)

    report_parser = subparsers.add_parser("report", help="Generate an HTML report")
    report_parser.add_argument(
        "--input",
        help="Fleet health JSON to render. Defaults to tests/fixtures/fleet-health.json.",
    )
    report_parser.add_argument(
        "--fixture",
        help="Alias for --input kept for fixture-driven local testing.",
    )
    report_parser.add_argument(
        "--output-dir",
        help="Directory for generated reports. Defaults to reports/generated.",
    )
    report_parser.set_defaults(func=command_report)

    collect_parser = subparsers.add_parser(
        "collect", help="Collect health summaries over SSH without changing server state"
    )
    collect_parser.add_argument(
        "--inventory",
        help="Inventory path. Defaults to config/servers.yaml.",
    )
    collect_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show SSH commands that would run without connecting.",
    )
    collect_parser.set_defaults(func=command_collect)

    check_parser = subparsers.add_parser("check", help="Run local rules and print findings")
    check_parser.add_argument(
        "--input",
        help="Fleet health JSON to check. Defaults to tests/fixtures/fleet-health.json.",
    )
    check_parser.add_argument(
        "--fixture",
        help="Alias for --input kept for fixture-driven local testing.",
    )
    check_parser.set_defaults(func=command_check)

    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Generate an HTML dashboard from run history"
    )
    dashboard_parser.add_argument(
        "--runs-dir",
        help="History runs directory. Defaults to history/runs.",
    )
    dashboard_parser.add_argument(
        "--output-dir",
        help="Directory for generated dashboard. Defaults to reports/generated.",
    )
    dashboard_parser.set_defaults(func=command_dashboard)

    catalog_parser = subparsers.add_parser(
        "catalog", help="Generate fleet capability catalog HTML and tracked JSON"
    )
    catalog_parser.add_argument(
        "--input",
        help="Fleet health JSON to catalog. Defaults to latest run history.",
    )
    catalog_parser.add_argument(
        "--output-dir",
        help="Directory for generated catalog HTML. Defaults to reports/generated.",
    )
    catalog_parser.add_argument(
        "--knowledge-path",
        help="Tracked catalog JSON path. Defaults to knowledge/fleet-catalog.json.",
    )
    catalog_parser.set_defaults(func=command_catalog)

    actions_parser = subparsers.add_parser("actions", help="Inspect or run actions")
    actions_subparsers = actions_parser.add_subparsers(
        dest="actions_command", required=True
    )
    actions_list_parser = actions_subparsers.add_parser(
        "list", help="List registered action IDs"
    )
    actions_list_parser.set_defaults(func=command_actions_list)

    actions_run_parser = actions_subparsers.add_parser(
        "run", help="Run one predefined action with approval"
    )
    actions_run_parser.add_argument("action_id", help="Registered action ID to run.")
    actions_run_parser.add_argument(
        "--server",
        required=True,
        help="Inventory server_id to target.",
    )
    actions_run_parser.add_argument(
        "--container",
        help="Docker container name for restart_docker_container.",
    )
    actions_run_parser.add_argument(
        "--service",
        help="Approved system service name for restart_service.",
    )
    actions_run_parser.add_argument(
        "--command",
        dest="admin_command",
        help="Root shell command for run_admin_command.",
    )
    actions_run_parser.add_argument(
        "--intent",
        help="Short reason for run_admin_command, stored in action history.",
    )
    actions_run_parser.add_argument(
        "--approval",
        help="Exact approval phrase for non-dry-run approval-required actions.",
    )
    actions_run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and record the action without executing it.",
    )
    actions_run_parser.add_argument(
        "--inventory",
        help="Inventory path. Defaults to config/servers.yaml.",
    )
    actions_run_parser.set_defaults(func=command_actions_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
