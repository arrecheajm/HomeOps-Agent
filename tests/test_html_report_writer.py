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
        self.assertIn("Fleet Catalog", html)
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

    def test_render_dashboard_links_existing_container_review(self):
        output_dir = Path("tests/.tmp/dashboard-with-container-review")
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)
        (output_dir / "container-review.html").write_text(
            "<html></html>",
            encoding="utf-8",
        )

        html = render_dashboard([self._run_summary()], output_dir)

        self.assertIn("Container Review", html)
        self.assertIn("container-review.html", html)

    def test_render_dashboard_surfaces_sanitized_container_inventory(self):
        run = self._targeted_container_run()
        run.servers[0]["docker"] = {
            "installed": True,
            "containers_total": 1,
            "containers_running": 1,
            "inventory_collected": True,
            "containers": [
                {
                    "name": "monitoring-grafana-1",
                    "image": "grafana/grafana:12",
                    "state": "running",
                    "health": "none",
                    "restart_policy": "unless-stopped",
                    "network_mode": "monitoring_default",
                    "compose_project": "monitoring",
                    "compose_service": "grafana",
                    "ports": [],
                    "mounts": [],
                }
            ],
        }

        html = render_dashboard([run], Path("reports/generated"))

        self.assertIn("Container Inventory", html)
        self.assertIn("monitoring-grafana-1", html)
        self.assertIn("Containers</dt><dd>1/1", html)

    def test_render_dashboard_preserves_known_servers_for_targeted_run(self):
        latest = self._targeted_container_run()
        previous_failure = self._partial_full_run_with_ispy_failure()
        older_success = self._three_server_run()

        html = render_dashboard(
            [latest, previous_failure, older_success],
            Path("reports/generated"),
        )

        self.assertIn("openvpn-server", html)
        self.assertIn("ispy-server", html)
        self.assertIn("container-host", html)
        self.assertIn("3</strong>", html)
        self.assertIn("1 checked, 0 failed", html)
        self.assertIn("Collected</dt><dd>yes", html)
        self.assertIn("Error", html)
        self.assertIn("Services unknown.", html)
        self.assertIn("Health command exited with code 255.", html)

    def test_render_dashboard_preserves_failed_server_for_partial_run(self):
        latest = self._targeted_container_run(
            collection_errors=[
                {
                    "server_id": "ispy-server",
                    "message": "Health command exited with code 255.",
                }
            ],
            servers_failed=1,
            counts={"critical": 1, "warning": 2, "info": 1},
            findings=[
                {
                    "severity": "critical",
                    "server_id": "ispy-server",
                    "code": "collection_failed",
                    "message": "Health command exited with code 255.",
                    "recommended_action_ids": [],
                }
            ],
        )
        previous = self._three_server_run()

        html = render_dashboard([latest, previous], Path("reports/generated"))

        self.assertIn("ispy-server", html)
        self.assertIn("failed", html)
        self.assertIn("Error", html)
        self.assertIn("Services unknown.", html)
        self.assertIn("Health command exited with code 255.", html)

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

    def _targeted_container_run(
        self,
        collection_errors: list[dict] | None = None,
        servers_failed: int = 0,
        counts: dict | None = None,
        findings: list[dict] | None = None,
    ) -> RunSummary:
        return RunSummary(
            run_id="2026-05-26T17-22-44Z",
            generated_at="2026-05-26T17:22:44Z",
            generated_dt=datetime.fromisoformat("2026-05-26T17:22:44+00:00"),
            fleet_path=Path("history/runs/2026-05-26T17-22-44Z/fleet-health.json"),
            servers_checked=1,
            servers_failed=servers_failed,
            counts=counts or {"critical": 0, "warning": 2, "info": 1},
            findings=findings
            or [
                {
                    "severity": "warning",
                    "server_id": "container-host",
                    "code": "docker_unhealthy_container",
                    "message": "Container watchtower is restarting.",
                    "recommended_action_ids": ["restart_docker_container"],
                }
            ],
            servers=[
                {
                    "server_id": "container-host",
                    "role": "container_host",
                    "hostname": "containerserver",
                    "updates": {
                        "pending_total": 7,
                        "reboot_required": True,
                    },
                    "services": [
                        {"name": "ssh", "state": "active", "enabled": False},
                        {"name": "docker", "state": "active", "enabled": True},
                    ],
                }
            ],
            collection_errors=collection_errors or [],
        )

    def _three_server_run(self) -> RunSummary:
        run = self._run_summary(
            run_id="2026-05-14T13-18-14Z",
            generated_at="2026-05-14T13:18:14Z",
        )
        return RunSummary(
            run_id=run.run_id,
            generated_at=run.generated_at,
            generated_dt=run.generated_dt,
            fleet_path=run.fleet_path,
            servers_checked=3,
            servers_failed=0,
            counts=run.counts,
            findings=run.findings,
            servers=[
                run.servers[0],
                {
                    "server_id": "ispy-server",
                    "role": "ispy_server",
                    "hostname": "ispyserver",
                    "updates": {
                        "pending_total": 71,
                        "reboot_required": True,
                    },
                    "services": [
                        {"name": "ssh", "state": "active", "enabled": False},
                        {"name": "AgentDVR", "state": "active", "enabled": True},
                    ],
                },
                {
                    "server_id": "container-host",
                    "role": "container_host",
                    "hostname": "containerserver",
                    "updates": {
                        "pending_total": 7,
                        "reboot_required": True,
                    },
                    "services": [
                        {"name": "ssh", "state": "active", "enabled": False},
                        {"name": "docker", "state": "active", "enabled": True},
                    ],
                },
            ],
            collection_errors=[],
        )

    def _partial_full_run_with_ispy_failure(self) -> RunSummary:
        return RunSummary(
            run_id="2026-05-26T17-00-16Z",
            generated_at="2026-05-26T17:00:16Z",
            generated_dt=datetime.fromisoformat("2026-05-26T17:00:16+00:00"),
            fleet_path=Path("history/runs/2026-05-26T17-00-16Z/fleet-health.json"),
            servers_checked=2,
            servers_failed=1,
            counts={"critical": 1, "warning": 3, "info": 2},
            findings=[
                {
                    "severity": "critical",
                    "server_id": "ispy-server",
                    "code": "collection_failed",
                    "message": "Health command exited with code 255.",
                    "recommended_action_ids": [],
                },
                {
                    "severity": "warning",
                    "server_id": "openvpn-server",
                    "code": "reboot_required",
                    "message": "The server reports that a reboot is required.",
                    "recommended_action_ids": ["reboot_server"],
                },
            ],
            servers=[
                {
                    "server_id": "openvpn-server",
                    "role": "openvpn_server",
                    "hostname": "vpnserver",
                    "updates": {
                        "pending_total": 53,
                        "reboot_required": True,
                    },
                    "services": [
                        {"name": "ssh", "state": "active", "enabled": False},
                        {"name": "openvpnas", "state": "active", "enabled": True},
                    ],
                },
                {
                    "server_id": "container-host",
                    "role": "container_host",
                    "hostname": "containerserver",
                    "updates": {
                        "pending_total": 7,
                        "reboot_required": True,
                    },
                    "services": [
                        {"name": "ssh", "state": "active", "enabled": False},
                        {"name": "docker", "state": "active", "enabled": True},
                    ],
                },
            ],
            collection_errors=[
                {
                    "server_id": "ispy-server",
                    "message": "Health command exited with code 255.",
                }
            ],
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
