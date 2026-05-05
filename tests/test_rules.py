from pathlib import Path
import unittest

from controller.main import load_json
from controller.rules import count_by_severity, evaluate_fleet


FIXTURE = Path("tests/fixtures/fleet-health.json")


class RulesTests(unittest.TestCase):
    def test_evaluate_fleet_detects_expected_findings(self):
        findings = evaluate_fleet(load_json(FIXTURE))
        codes = {finding["code"] for finding in findings}

        self.assertIn("disk_usage_high", codes)
        self.assertIn("docker_unhealthy_container", codes)
        self.assertIn("security_updates_pending", codes)
        self.assertIn("updates_pending", codes)

    def test_count_by_severity_counts_fixture_findings(self):
        findings = evaluate_fleet(load_json(FIXTURE))
        counts = count_by_severity(findings)

        self.assertEqual(counts["critical"], 0)
        self.assertEqual(counts["warning"], 4)
        self.assertEqual(counts["info"], 1)


if __name__ == "__main__":
    unittest.main()
