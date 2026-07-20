import json
from pathlib import Path
import unittest

from controller.container_evidence import (
    load_container_review_evidence,
    normalize_container_review_evidence,
)


class ContainerEvidenceTests(unittest.TestCase):
    def test_normalizes_allowlisted_storage_and_database_evidence(self):
        evidence = normalize_container_review_evidence(
            {
                "observed_at": "2026-07-20T18:36:00Z",
                "secret": "must not survive",
                "storage": {
                    "external_device_detected": False,
                    "targets": [
                        {
                            "path": "/mnt/storage1",
                            "backing_target": "/",
                            "aggregate_bytes": "12288",
                            "sentinel_present": False,
                            "file_names": ["private.pdf"],
                        }
                    ],
                },
                "databases": [
                    {
                        "container": "mysql57",
                        "volume_bytes": "220450816",
                        "environment": {"MYSQL_ROOT_PASSWORD": "secret"},
                    }
                ],
            }
        )

        self.assertNotIn("secret", evidence)
        self.assertNotIn("file_names", evidence["storage"]["targets"][0])
        self.assertNotIn("environment", evidence["databases"][0])
        self.assertEqual(evidence["storage"]["targets"][0]["aggregate_bytes"], 12288)
        self.assertEqual(evidence["databases"][0]["volume_bytes"], 220450816)

    def test_loads_evidence_for_requested_server_only(self):
        path = Path("tests/.tmp/container-review-evidence.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "servers": {
                        "container-host": {"observed_at": "2026-07-20T18:36:00Z"},
                        "other": {"observed_at": "never"},
                    }
                }
            ),
            encoding="utf-8",
        )

        evidence = load_container_review_evidence(path, "container-host")

        self.assertEqual(evidence["observed_at"], "2026-07-20T18:36:00Z")


if __name__ == "__main__":
    unittest.main()
