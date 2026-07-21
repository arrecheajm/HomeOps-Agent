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
        self.assertIn("--storage.tsdb.retention.size=4GB", (STACK_DIR / "compose.yaml").read_text(encoding="utf-8"))

    def test_dashboard_is_valid_json_with_core_homeops_panels(self):
        dashboard = json.loads(
            (STACK_DIR / "grafana/dashboards/homeops-overview.json").read_text(
                encoding="utf-8"
            )
        )
        titles = {panel["title"] for panel in dashboard["panels"]}

        self.assertEqual(dashboard["uid"], "homeops-overview")
        self.assertIn("Host CPU Used", titles)
        self.assertIn("Root Filesystem Used", titles)
        self.assertIn("Top Container Memory", titles)
        self.assertIn("Scrape Target Health", titles)


if __name__ == "__main__":
    unittest.main()
