from datetime import datetime, timezone
from pathlib import Path
import shutil
import unittest

from controller.history import ActionSummary, RunSummary
from controller.html_report_writer import render_dashboard, write_dashboard


class HtmlReportWriterTests(unittest.TestCase):
    def test_render_dashboard_includes_latest_summary_and_timeline(self):
        run = self._run_summary()
        earlier_run = self._run_summary(
            run_id="2026-05-05T12-00-00Z",
            generated_at="2026-05-05T12:00:00Z",
            warnings=0,
            pending_updates=12,
            reboot_required=False,
        )

        html = render_dashboard(
            [run, earlier_run],
            Path("reports/generated"),
            [self._action_summary()],
        )

        self.assertIn("HomeOps Dashboard", html)
        self.assertIn("Latest Server State", html)
        self.assertIn("Historical Data", html)
        self.assertIn("Finding Trend", html)
        self.assertIn("Pending Updates", html)
        self.assertIn("Reboot And Docker Watch", html)
        self.assertIn("Action History", html)
        self.assertIn("restart_docker_container", html)
        self.assertIn("watchtower", html)
        self.assertIn("Agent History", html)
        self.assertIn("Agent Action Outcomes", html)
        self.assertIn("Agent Action Timeline", html)
        self.assertIn("approval_required", html)
        self.assertIn("dry_run", html)
        self.assertIn("Run Timeline", html)
        self.assertIn("reboot_required", html)
        self.assertIn("openvpn-server", html)
        self.assertIn("openvpnas", html)

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

    def test_render_dashboard_includes_agent_history_without_runs(self):
        html = render_dashboard([], Path("reports/generated"), [self._action_summary()])

        self.assertIn("No Runs Found", html)
        self.assertIn("Agent History", html)
        self.assertIn("Agent Action Timeline", html)
        self.assertIn("restart_docker_container", html)

    def _run_summary(
        self,
        run_id: str = "2026-05-06T12-00-00Z",
        generated_at: str = "2026-05-06T12:00:00Z",
        warnings: int = 1,
        pending_updates: int = 48,
        reboot_required: bool = True,
    ) -> RunSummary:
        findings = []
        if warnings:
            findings.append(
                {
                    "severity": "warning",
                    "server_id": "openvpn-server",
                    "code": "reboot_required",
                    "message": "The server reports that a reboot is required.",
                    "recommended_action_ids": ["reboot_server"],
                }
            )

        return RunSummary(
            run_id=run_id,
            generated_at=generated_at,
            generated_dt=datetime.fromisoformat(generated_at.replace("Z", "+00:00")),
            fleet_path=Path(f"history/runs/{run_id}/fleet-health.json"),
            servers_checked=1,
            servers_failed=0,
            counts={"critical": 0, "warning": warnings, "info": 0},
            findings=findings,
            servers=[
                {
                    "server_id": "openvpn-server",
                    "role": "openvpn_server",
                    "hostname": "vpnserver",
                    "updates": {
                        "pending_total": pending_updates,
                        "reboot_required": reboot_required,
                    },
                    "services": [
                        {"name": "ssh", "state": "active", "enabled": False},
                        {"name": "openvpnas", "state": "active", "enabled": True},
                    ],
                }
            ],
            collection_errors=[],
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
