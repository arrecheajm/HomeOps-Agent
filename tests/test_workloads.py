import json
from pathlib import Path
import unittest

from controller.workloads import load_workloads, normalize_workloads


class WorkloadManifestTests(unittest.TestCase):
    def test_normalizes_and_sorts_workloads(self):
        manifest = normalize_workloads(
            {
                "network_scope": "lan_only",
                "workloads": [
                    {
                        "workload_id": "documents",
                        "phase": 4,
                        "state": "invalid",
                        "storage_class": "mixed",
                        "deployment_enabled": False,
                        "services": ["paperless-ngx"],
                        "secret": "excluded",
                    },
                    {
                        "workload_id": "monitoring",
                        "phase": 0,
                        "state": "redeploy",
                        "storage_class": "internal",
                    },
                ],
            }
        )

        self.assertEqual(
            [item["workload_id"] for item in manifest["workloads"]],
            ["monitoring", "documents"],
        )
        self.assertEqual(manifest["workloads"][1]["state"], "planned")
        self.assertNotIn("secret", manifest["workloads"][1])
        self.assertFalse(manifest["workloads"][1]["deployment_enabled"])

    def test_loads_requested_server_manifest(self):
        path = Path("tests/.tmp/workloads.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "servers": {
                        "container-host": {
                            "workloads": [{"workload_id": "monitoring", "phase": 0}]
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        manifest = load_workloads(path, "container-host")

        self.assertEqual(manifest["workloads"][0]["workload_id"], "monitoring")

    def test_preserves_acceptance_pending_deployment_state(self):
        manifest = normalize_workloads(
            {
                "workloads": [
                    {
                        "workload_id": "monitoring",
                        "state": "acceptance_pending",
                        "deployment_enabled": True,
                    }
                ]
            }
        )

        self.assertEqual(manifest["workloads"][0]["state"], "acceptance_pending")
        self.assertTrue(manifest["workloads"][0]["deployment_enabled"])


if __name__ == "__main__":
    unittest.main()
