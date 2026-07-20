import unittest

from controller.schemas import validate_server_health


class SchemaTests(unittest.TestCase):
    def test_accepts_sanitized_docker_inventory(self):
        validate_server_health(
            {
                "docker": {
                    "installed": True,
                    "inventory_collected": True,
                    "containers": [
                        {
                            "name": "paperless",
                            "image": "paperlessngx/paperless-ngx:2",
                            "state": "running",
                            "health": "healthy",
                            "restart_policy": "unless-stopped",
                            "network_mode": "paperless_default",
                            "compose_project": "paperless",
                            "compose_service": "webserver",
                            "ports": [
                                {
                                    "container_port": "8000/tcp",
                                    "host_ip": "192.168.86.58",
                                    "host_port": "8000",
                                }
                            ],
                            "mounts": [
                                {
                                    "type": "bind",
                                    "source": "/srv/paperless",
                                    "destination": "/usr/src/paperless/media",
                                    "read_only": False,
                                }
                            ],
                        }
                    ],
                }
            }
        )

    def test_rejects_non_boolean_mount_access(self):
        with self.assertRaisesRegex(ValueError, "read_only must be a boolean"):
            validate_server_health(
                {
                    "docker": {
                        "containers": [
                            {
                                "mounts": [
                                    {
                                        "type": "bind",
                                        "source": "/srv/data",
                                        "destination": "/data",
                                        "read_only": "false",
                                    }
                                ]
                            }
                        ]
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()
