from datetime import datetime, timezone
from pathlib import Path
import shutil
import unittest

from controller.history import RunSummary
from controller.html_report_writer import render_dashboard, write_dashboard


class HtmlReportWriterTests(unittest.TestCase):
    def test_render_dashboard_includes_latest_summary_and_timeline(self):
        run = self._run_summary()

        html = render_dashboard([run], Path("reports/generated"))

        self.assertIn("HomeOps Dashboard", html)
        self.assertIn("Latest Server State", html)
        self.assertIn("Run Timeline", html)
        self.assertIn("reboot_required", html)
        self.assertIn("openvpn-server", html)

    def test_write_dashboard_creates_index_html(self):
        output_dir = Path("tests/.tmp/html-dashboard")
        if output_dir.exists():
            shutil.rmtree(output_dir)

        path = write_dashboard([self._run_summary()], output_dir)

        self.assertEqual(path.name, "index.html")
        self.assertTrue(path.exists())
        self.assertIn(
            "HomeOps Dashboard",
            path.read_text(encoding="utf-8"),
        )

    def _run_summary(self) -> RunSummary:
        return RunSummary(
            run_id="2026-05-06T12-00-00Z",
            generated_at="2026-05-06T12:00:00Z",
            generated_dt=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
            fleet_path=Path("history/runs/2026-05-06T12-00-00Z/fleet-health.json"),
            report_path=Path("reports/generated/homeops-report-2026-05-06T12-00-00Z.md"),
            servers_checked=1,
            servers_failed=0,
            counts={"critical": 0, "warning": 1, "info": 0},
            findings=[
                {
                    "severity": "warning",
                    "server_id": "openvpn-server",
                    "code": "reboot_required",
                    "message": "The server reports that a reboot is required.",
                    "recommended_action_ids": ["reboot_server"],
                }
            ],
            servers=[
                {
                    "server_id": "openvpn-server",
                    "role": "openvpn_server",
                    "hostname": "vpnserver",
                    "updates": {"pending_total": 48, "reboot_required": True},
                }
            ],
            collection_errors=[],
        )


if __name__ == "__main__":
    unittest.main()
