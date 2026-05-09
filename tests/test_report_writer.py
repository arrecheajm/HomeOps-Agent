from pathlib import Path
import shutil
import unittest

from controller.history import ActionSummary
from controller.main import apply_local_rules, load_json
from controller.report_writer import render_report, write_report
from datetime import datetime, timezone


FIXTURE = Path("tests/fixtures/fleet-health.json")


class ReportWriterTests(unittest.TestCase):
    def test_render_report_includes_expected_sections(self):
        fleet = apply_local_rules(load_json(FIXTURE))
        report = render_report(fleet)

        self.assertIn("# HomeOps Maintenance Report", report)
        self.assertIn("## Fleet Summary", report)
        self.assertIn("## Warnings", report)
        self.assertIn("`container-host`", report)
        self.assertIn("`restart_docker_container`", report)

    def test_render_report_includes_action_history(self):
        fleet = apply_local_rules(load_json(FIXTURE))
        report = render_report(fleet, [self._action_summary()])

        self.assertIn("## Actions Taken", report)
        self.assertIn("restart_docker_container", report)
        self.assertIn("watchtower", report)
        self.assertIn("dry_run", report)

    def test_write_report_creates_markdown_file(self):
        output_dir = Path("tests/.tmp/report-writer")
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)

        fleet = apply_local_rules(load_json(FIXTURE))
        report_path = write_report(fleet, output_dir)

        self.assertTrue(report_path.exists())
        self.assertEqual(report_path.suffix, ".md")
        self.assertTrue(
            report_path.read_text(encoding="utf-8").startswith(
                "# HomeOps Maintenance Report"
            )
        )

    def _action_summary(self) -> ActionSummary:
        return ActionSummary(
            timestamp="2026-05-09T18:49:56Z",
            timestamp_dt=datetime(2026, 5, 9, 18, 49, 56, tzinfo=timezone.utc),
            record_path=Path("history/actions/action.json"),
            server_id="container-host",
            action_id="restart_docker_container",
            status="dry_run",
            risk="approval_required",
            dry_run=True,
            arguments={"container": "watchtower"},
            approval_source="dry_run",
            command=["ssh", "container-host", "docker", "restart", "watchtower"],
            exit_code=None,
            message="Action was validated but not executed.",
        )


if __name__ == "__main__":
    unittest.main()
