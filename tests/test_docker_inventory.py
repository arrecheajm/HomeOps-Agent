import json
from pathlib import Path
import unittest

from controller.docker_inventory import (
    inventory_collected,
    load_container_classifications,
    mount_labels,
    normalize_docker_inventory,
    port_labels,
)


class DockerInventoryTests(unittest.TestCase):
    def test_normalizes_sorts_and_classifies_exposure(self):
        docker = {
            "inventory_collected": True,
            "containers": [
                {
                    "name": "prometheus\n",
                    "image": "prom/prometheus:v3",
                    "state": "running",
                    "health": "healthy",
                    "restart_policy": "unless-stopped",
                    "network_mode": "monitoring_default",
                    "compose_project": "monitoring",
                    "compose_service": "prometheus",
                    "ports": [
                        {
                            "container_port": "9090/tcp",
                            "host_ip": "0.0.0.0",
                            "host_port": "9090",
                        }
                    ],
                    "mounts": [
                        {
                            "type": "bind",
                            "source": "/srv/prometheus",
                            "destination": "/prometheus",
                            "read_only": False,
                        }
                    ],
                    "environment": ["SECRET=must-not-survive"],
                },
                {
                    "name": "alertmanager",
                    "image": "prom/alertmanager:v1",
                    "state": "running",
                    "network_mode": "host",
                },
            ],
        }

        inventory = normalize_docker_inventory(docker)

        self.assertTrue(inventory_collected(docker))
        self.assertEqual([item["name"] for item in inventory], ["alertmanager", "prometheus"])
        self.assertEqual(inventory[0]["exposure"], "host network")
        self.assertEqual(inventory[1]["exposure"], "published")
        self.assertNotIn("environment", inventory[1])
        self.assertEqual(
            port_labels(inventory[1]),
            ["0.0.0.0:9090 -> 9090/tcp"],
        )
        self.assertEqual(
            mount_labels(inventory[1]),
            ["/srv/prometheus -> /prometheus (rw)"],
        )

    def test_missing_inventory_is_distinct_from_empty_inventory(self):
        self.assertFalse(inventory_collected({"installed": True}))
        self.assertTrue(
            inventory_collected(
                {"installed": True, "inventory_collected": True, "containers": []}
            )
        )

    def test_loads_local_classification_without_other_config_fields(self):
        path = Path("tests/.tmp/container-classifications.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "servers": {
                        "container-host": {
                            "grafana": {
                                "classification": "redeploy",
                                "rationale": "Pin the image.",
                                "secret": "must-not-survive",
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        classifications = load_container_classifications(path, "container-host")

        self.assertEqual(
            classifications,
            {
                "grafana": {
                    "classification": "redeploy",
                    "rationale": "Pin the image.",
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
