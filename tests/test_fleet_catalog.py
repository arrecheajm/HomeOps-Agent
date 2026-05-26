from datetime import datetime
from pathlib import Path
import json
import shutil
import unittest

from controller.fleet_catalog import build_fleet_catalog, render_fleet_catalog, write_fleet_catalog
from controller.history import RunSummary


class FleetCatalogTests(unittest.TestCase):
    def test_build_fleet_catalog_extracts_capability_guidance(self):
        catalog = build_fleet_catalog(self._run_summary())

        self.assertEqual(catalog["generated_at"], "2026-05-10T19:49:53Z")
        self.assertEqual(catalog["fleet_summary"]["servers"], 2)
        self.assertEqual(catalog["fleet_summary"]["cpu_threads"], 6)
        self.assertEqual(catalog["fleet_summary"]["docker_hosts"], 1)
        container = self._server(catalog, "container-host")
        self.assertIn("Docker application host", container["capabilities"])
        self.assertIn("Docker issue: watchtower", container["constraints"])
        self.assertIn(
            "Prefer this host for Codex lab experiments and Docker-backed applications.",
            container["placement_guidance"],
        )
        self.assertEqual(container["hardware"]["virtualization"], "none")
        self.assertEqual(container["services"][1]["state"], "failed")
        self.assertIn("Service issue: docker", container["constraints"])

    def test_render_fleet_catalog_includes_server_cards(self):
        catalog = build_fleet_catalog(self._run_summary())
        html = render_fleet_catalog(catalog, Path("reports/generated"))

        self.assertIn("HomeOps Fleet Catalog", html)
        self.assertIn("Fleet Placement Guidance", html)
        self.assertIn("container-host", html)
        self.assertIn("openvpn-server", html)

    def test_build_fleet_catalog_preserves_failed_server_from_fallback(self):
        partial_run = RunSummary(
            run_id="2026-05-26T17-00-16Z",
            generated_at="2026-05-26T17:00:16Z",
            generated_dt=datetime.fromisoformat("2026-05-26T17:00:16+00:00"),
            fleet_path=Path("history/runs/2026-05-26T17-00-16Z/fleet-health.json"),
            servers_checked=1,
            servers_failed=1,
            counts={"critical": 1, "warning": 0, "info": 0},
            findings=[
                {
                    "severity": "critical",
                    "server_id": "ispy-server",
                    "code": "collection_failed",
                    "message": "Health command exited with code 255.",
                }
            ],
            servers=[self._run_summary().servers[0]],
            collection_errors=[
                {
                    "server_id": "ispy-server",
                    "message": "Health command exited with code 255.",
                }
            ],
        )

        catalog = build_fleet_catalog(
            partial_run,
            fallback_servers={"ispy-server": self._fallback_ispy_catalog()},
        )

        self.assertEqual(catalog["fleet_summary"]["servers"], 2)
        self.assertEqual(catalog["fleet_summary"]["collection_failed"], 1)
        ispy = self._server(catalog, "ispy-server")
        self.assertEqual(ispy["collection_status"], "failed_latest")
        self.assertEqual(
            ispy["last_successful_collected_at"],
            "2026-05-12T22:42:04Z",
        )
        self.assertEqual(ispy["current_findings"][0]["code"], "collection_failed")
        self.assertIn("Latest collection failed", ispy["constraints"])
        self.assertIn("AgentDVR workload", ispy["capabilities"])

    def test_build_fleet_catalog_preserves_all_fallback_servers_for_targeted_run(self):
        targeted_run = RunSummary(
            run_id="2026-05-26T17-22-44Z",
            generated_at="2026-05-26T17:22:44Z",
            generated_dt=datetime.fromisoformat("2026-05-26T17:22:44+00:00"),
            fleet_path=Path("history/runs/2026-05-26T17-22-44Z/fleet-health.json"),
            servers_checked=1,
            servers_failed=0,
            counts={"critical": 0, "warning": 0, "info": 0},
            findings=[],
            servers=[self._run_summary().servers[1]],
            collection_errors=[],
        )

        fallback_catalog = build_fleet_catalog(self._run_summary())
        catalog = build_fleet_catalog(
            targeted_run,
            fallback_servers={
                "openvpn-server": self._server(fallback_catalog, "openvpn-server"),
                "ispy-server": self._fallback_ispy_catalog(),
            },
            include_all_fallback_servers=True,
        )

        self.assertEqual(catalog["fleet_summary"]["servers"], 3)
        self.assertEqual(catalog["fleet_summary"]["not_collected"], 2)
        ispy = self._server(catalog, "ispy-server")
        self.assertEqual(ispy["collection_status"], "not_in_latest_run")
        self.assertIn("Not collected in latest run", ispy["constraints"])

    def test_write_fleet_catalog_writes_json_and_html(self):
        output_dir = Path("tests/.tmp/fleet-catalog-output")
        knowledge_path = Path("tests/.tmp/fleet-catalog/fleet-catalog.json")
        for path in (output_dir, knowledge_path.parent):
            if path.exists():
                shutil.rmtree(path)

        written_knowledge, html_path = write_fleet_catalog(
            self._run_summary(),
            output_dir,
            knowledge_path,
        )

        self.assertTrue(written_knowledge.exists())
        self.assertTrue(html_path.exists())
        payload = json.loads(written_knowledge.read_text(encoding="utf-8"))
        self.assertEqual(payload["source"]["run_id"], "2026-05-10T19-49-53Z")

    def _server(self, catalog: dict, server_id: str) -> dict:
        for server in catalog["servers"]:
            if server["server_id"] == server_id:
                return server
        raise AssertionError(f"missing server: {server_id}")

    def _fallback_ispy_catalog(self) -> dict:
        return {
            "server_id": "ispy-server",
            "hostname": "ispyserver",
            "role": "ispy_server",
            "role_label": "Security Cameras",
            "collected_at": "2026-05-12T22:42:04Z",
            "os": {
                "name": "Ubuntu",
                "version": "24.04",
                "kernel": "6.8.0-100-generic",
            },
            "hardware": {
                "architecture": "x86_64",
                "cpu_model": "Intel CPU",
                "memory_total_mb": 7830,
                "virtualization": "none",
            },
            "resources": {
                "cpu_count": 4,
                "load_1m": 0.39,
                "memory_used_percent": 10.3,
                "swap_used_percent": 0.0,
                "uptime_days": 88.1,
            },
            "storage": {
                "disks": [{"mount": "/", "used_percent": 12, "free_gb": 82}],
                "root_free_gb": 82,
                "root_used_percent": 12,
                "total_reported_free_gb": 82,
            },
            "services": [
                {"name": "ssh", "state": "active", "enabled": False},
                {"name": "AgentDVR", "state": "active", "enabled": True},
                {"name": "ispy", "state": "failed", "enabled": True},
            ],
            "docker": {
                "installed": False,
                "containers_total": 0,
                "containers_running": 0,
                "unhealthy": [],
            },
            "maintenance": {
                "pending_updates": 71,
                "pending_security_updates": 0,
                "reboot_required": True,
            },
            "current_findings": [],
            "capabilities": ["Security camera service host", "AgentDVR workload"],
            "constraints": [
                "Reboot required",
                "71 package updates pending",
                "Camera recording interruption risk",
            ],
            "placement_guidance": ["Prioritize AgentDVR and camera reliability."],
        }

    def _run_summary(self) -> RunSummary:
        return RunSummary(
            run_id="2026-05-10T19-49-53Z",
            generated_at="2026-05-10T19:49:53Z",
            generated_dt=datetime.fromisoformat("2026-05-10T19:49:53+00:00"),
            fleet_path=Path("history/runs/2026-05-10T19-49-53Z/fleet-health.json"),
            servers_checked=2,
            servers_failed=0,
            counts={"critical": 0, "warning": 1, "info": 1},
            findings=[
                {
                    "severity": "warning",
                    "server_id": "container-host",
                    "code": "docker_unhealthy_container",
                    "message": "Container watchtower is reporting Restarting.",
                },
                {
                    "severity": "info",
                    "server_id": "openvpn-server",
                    "code": "updates_pending",
                    "message": "53 package updates are pending.",
                },
            ],
            servers=[
                {
                    "server_id": "openvpn-server",
                    "role": "openvpn_server",
                    "hostname": "vpnserver",
                    "collected_at": "2026-05-10T19:49:58Z",
                    "os": {
                        "name": "Ubuntu",
                        "version": "24.04",
                        "kernel": "6.8.0-111-generic",
                    },
                    "hardware": {
                        "architecture": "x86_64",
                        "cpu_model": "Intel CPU",
                        "memory_total_mb": 8192,
                        "virtualization": "none\nnone",
                    },
                    "uptime_seconds": 178581,
                    "resources": {
                        "cpu_count": 2,
                        "load_1m": 0.3,
                        "memory_used_percent": 19.8,
                        "swap_used_percent": 0.0,
                    },
                    "disk": [
                        {"mount": "/", "used_percent": 9, "free_gb": 85},
                    ],
                    "updates": {
                        "pending_total": 53,
                        "pending_security": 0,
                        "reboot_required": False,
                    },
                    "services": [
                        {"name": "ssh", "state": "active", "enabled": False},
                        {"name": "openvpnas", "state": "active", "enabled": True},
                    ],
                    "docker": {"installed": False},
                },
                {
                    "server_id": "container-host",
                    "role": "container_host",
                    "hostname": "containerserver",
                    "collected_at": "2026-05-10T19:50:04Z",
                    "os": {
                        "name": "Ubuntu",
                        "version": "24.04",
                        "kernel": "6.8.0-101-generic",
                    },
                    "hardware": {
                        "architecture": "x86_64",
                        "cpu_model": "Intel CPU",
                        "memory_total_mb": 8192,
                        "virtualization": "none\nnone",
                    },
                    "uptime_seconds": 259051,
                    "resources": {
                        "cpu_count": 4,
                        "load_1m": 0.3,
                        "memory_used_percent": 16.0,
                        "swap_used_percent": 0.0,
                    },
                    "disk": [
                        {"mount": "/", "used_percent": 14, "free_gb": 81},
                    ],
                    "updates": {
                        "pending_total": 0,
                        "pending_security": 0,
                        "reboot_required": True,
                    },
                    "services": [
                        {"name": "ssh", "state": "active", "enabled": False},
                        {"name": "docker", "state": "failed\nunknown", "enabled": True},
                    ],
                    "docker": {
                        "installed": True,
                        "containers_total": 9,
                        "containers_running": 9,
                        "unhealthy": [
                            {
                                "name": "watchtower",
                                "status": "Restarting",
                            }
                        ],
                    },
                },
            ],
            collection_errors=[],
        )


if __name__ == "__main__":
    unittest.main()
