"""Command line entrypoint for HomeOps controller."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import action_registry, collector, config, inventory, rules
from .report_writer import write_report
from .ssh_client import build_ssh_command


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
    updated["findings"] = rules.evaluate_fleet(updated)
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
    fleet = apply_local_rules(load_json(resolve_input_path(args)))
    output_dir = Path(args.output_dir) if args.output_dir else config.GENERATED_REPORTS_DIR
    report_path = write_report(fleet, output_dir)

    counts = rules.count_by_severity(fleet.get("findings") or [])
    print(f"Wrote report: {report_path}")
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

    report_path = None
    if not args.no_report:
        report_path = write_report(fleet, config.GENERATED_REPORTS_DIR)

    counts = rules.count_by_severity(fleet.get("findings") or [])
    print(f"Run directory: {run_dir}")
    print(f"Wrote fleet health: {fleet_path}")
    if report_path:
        print(f"Wrote report: {report_path}")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HomeOps controller")
    subparsers = parser.add_subparsers(dest="command", required=True)

    report_parser = subparsers.add_parser("report", help="Generate a Markdown report")
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
        "collect", help="Collect read-only health summaries over SSH"
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
    collect_parser.add_argument(
        "--no-report",
        action="store_true",
        help="Collect and write fleet JSON without writing a Markdown report.",
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

    actions_parser = subparsers.add_parser("actions", help="Inspect or run actions")
    actions_subparsers = actions_parser.add_subparsers(
        dest="actions_command", required=True
    )
    actions_list_parser = actions_subparsers.add_parser(
        "list", help="List registered action IDs"
    )
    actions_list_parser.set_defaults(func=command_actions_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
