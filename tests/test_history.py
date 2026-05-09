from pathlib import Path
import json
import shutil
import unittest
from datetime import datetime, timezone

from controller.history import discover_action_summaries, discover_run_summaries, group_runs_by_period


class HistoryTests(unittest.TestCase):
    def test_discover_run_summaries_groups_operating_periods(self):
        root = Path("tests/.tmp/history-runs")
        reports = Path("tests/.tmp/history-reports")
        if root.exists():
            shutil.rmtree(root)
        if reports.exists():
            shutil.rmtree(reports)
        root.mkdir(parents=True)
        reports.mkdir(parents=True)

        self._write_run(root, "2026-05-06T12-00-00Z", "2026-05-06T12:00:00Z")
        self._write_run(root, "2026-05-05T12-00-00Z", "2026-05-05T12:00:00Z")
        self._write_run(root, "2026-05-01T12-00-00Z", "2026-05-01T12:00:00Z")
        self._write_run(root, "2026-04-20T12-00-00Z", "2026-04-20T12:00:00Z")

        runs = discover_run_summaries(root, reports)
        groups = group_runs_by_period(
            runs,
            now=datetime(2026, 5, 6, 16, 0, tzinfo=timezone.utc),
        )

        labels = [label for label, _runs in groups]

        self.assertEqual(
            labels,
            ["Today", "This Week", "Earlier This Month", "April 2026"],
        )

    def test_discover_run_summaries_counts_findings(self):
        root = Path("tests/.tmp/history-counts")
        reports = Path("tests/.tmp/history-count-reports")
        if root.exists():
            shutil.rmtree(root)
        if reports.exists():
            shutil.rmtree(reports)
        root.mkdir(parents=True)
        reports.mkdir(parents=True)

        self._write_run(
            root,
            "2026-05-06T12-00-00Z",
            "2026-05-06T12:00:00Z",
            findings=[
                {"severity": "warning", "server_id": "ispy-server"},
                {"severity": "info", "server_id": "openvpn-server"},
            ],
        )

        runs = discover_run_summaries(root, reports)

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].counts["warning"], 1)
        self.assertEqual(runs[0].counts["info"], 1)

    def test_discover_action_summaries_loads_action_records(self):
        root = Path("tests/.tmp/action-summary-history")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)

        record = {
            "timestamp": "2026-05-09T18:49:56Z",
            "server_id": "container-host",
            "action_id": "restart_docker_container",
            "status": "dry_run",
            "risk": "approval_required",
            "dry_run": True,
            "arguments": {"container": "watchtower"},
            "approval_source": "dry_run",
            "command": ["ssh", "container-host", "docker", "restart", "watchtower"],
            "exit_code": None,
            "message": "Action was validated but not executed.",
        }
        (root / "record.json").write_text(json.dumps(record), encoding="utf-8")

        actions = discover_action_summaries(root)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].server_id, "container-host")
        self.assertEqual(actions[0].action_id, "restart_docker_container")
        self.assertTrue(actions[0].dry_run)
        self.assertEqual(actions[0].arguments["container"], "watchtower")

    def _write_run(
        self,
        root: Path,
        run_id: str,
        generated_at: str,
        findings: list[dict] | None = None,
    ) -> None:
        run_dir = root / run_id
        run_dir.mkdir()
        payload = {
            "generated_at": generated_at,
            "servers_checked": 2,
            "servers_failed": 0,
            "collection_errors": [],
            "findings": findings or [],
            "servers": [],
        }
        (run_dir / "fleet-health.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
