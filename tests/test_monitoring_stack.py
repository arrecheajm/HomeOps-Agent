import json
from pathlib import Path
import unittest


STACK_DIR = Path("stacks/monitoring")


class MonitoringStackTests(unittest.TestCase):
    def test_compose_pins_images_and_avoids_latest(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertNotIn(":latest", compose)
        self.assertIn("grafana/grafana:13.1.0", compose)
        self.assertIn("prom/prometheus:v3.12.0", compose)
        self.assertIn("prom/node-exporter:v1.11.1", compose)
        self.assertIn("ghcr.io/google/cadvisor:v0.57.0", compose)
        self.assertEqual(compose.count("@sha256:"), 4)

    def test_only_grafana_has_a_published_port(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertEqual(compose.count("    ports:\n"), 1)
        self.assertIn('${HOMEOPS_LAN_IP:-192.168.86.58}:3000:3000', compose)
        self.assertNotIn(":8080:8080", compose)
        self.assertNotIn(":9090:9090", compose)
        self.assertNotIn(":9100:9100", compose)

    def test_prometheus_keeps_existing_scrape_targets(self):
        prometheus = (STACK_DIR / "prometheus/prometheus.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("node-exporter:9100", prometheus)
        self.assertIn("cadvisor:8080", prometheus)
        self.assertIn("192.168.86.25:9100", prometheus)
        self.assertIn("192.168.86.27:9100", prometheus)
        self.assertIn(
            "- job_name: node-exporter\n"
            "    static_configs:\n"
            "      - targets:\n"
            "          - node-exporter:9100\n"
            "        labels:\n"
            "          server_id: container-host",
            prometheus,
        )
        self.assertIn(
            "- job_name: openvpn-server\n"
            "    static_configs:\n"
            "      - targets:\n"
            "          - 192.168.86.25:9100\n"
            "        labels:\n"
            "          server_id: openvpn-server",
            prometheus,
        )
        self.assertIn(
            "- job_name: ispy-server\n"
            "    static_configs:\n"
            "      - targets:\n"
            "          - 192.168.86.27:9100\n"
            "        labels:\n"
            "          server_id: ispy-server",
            prometheus,
        )
        self.assertIn("--storage.tsdb.retention.size=4GB", (STACK_DIR / "compose.yaml").read_text(encoding="utf-8"))

    def test_dashboard_is_valid_json_with_core_homeops_panels(self):
        dashboard = json.loads(
            (STACK_DIR / "grafana/dashboards/homeops-overview.json").read_text(
                encoding="utf-8"
            )
        )
        titles = {panel["title"] for panel in dashboard["panels"]}

        self.assertEqual(dashboard["uid"], "homeops-overview")
        self.assertEqual(
            dashboard["links"],
            [
                {
                    "asDropdown": False,
                    "icon": "external link",
                    "includeVars": False,
                    "keepTime": False,
                    "tags": [],
                    "targetBlank": True,
                    "title": "HomeOps Mission Control",
                    "tooltip": "Open the household HomeOps landing page",
                    "type": "link",
                    "url": "http://192.168.86.58:8081",
                }
            ],
        )
        self.assertIn("Host CPU Used", titles)
        self.assertIn("Root Filesystem Used", titles)
        self.assertIn("Top Container Memory", titles)
        self.assertIn("Scrape Target Health", titles)
        host_panels = {
            panel["title"]: panel
            for panel in dashboard["panels"]
            if panel["title"] in {
                "Host CPU Used",
                "Host Memory Used",
                "Root Filesystem Used",
                "Host CPU Trend",
            }
        }
        self.assertEqual(
            {panel["targets"][0]["legendFormat"] for panel in host_panels.values()},
            {"{{server_id}}"},
        )
        self.assertNotIn("{{instance}}", json.dumps(dashboard))
        target_health = next(
            panel
            for panel in dashboard["panels"]
            if panel["title"] == "Scrape Target Health"
        )
        organize = target_health["transformations"][0]["options"]
        self.assertTrue(organize["excludeByName"]["instance"])
        self.assertEqual(organize["renameByName"]["server_id"], "Server")

    def test_grafana_disables_plugin_preinstall_and_has_optional_directories(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn('GF_PLUGINS_PREINSTALL_DISABLED: "true"', compose)
        self.assertIn('GF_PLUGINS_PREINSTALL_AUTO_UPDATE: "false"', compose)
        self.assertTrue(
            (STACK_DIR / "grafana/provisioning/alerting/README.md").is_file()
        )
        self.assertTrue(
            (STACK_DIR / "grafana/provisioning/plugins/README.md").is_file()
        )

    def test_grafana_secret_is_bootstrapped_outside_the_container(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertNotIn("GF_SECURITY_ADMIN_PASSWORD__FILE", compose)
        self.assertNotIn("/run/secrets/grafana_admin_password", compose)
        self.assertNotIn("secrets:", compose)


if __name__ == "__main__":
    unittest.main()
