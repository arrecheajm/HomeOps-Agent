import json
from pathlib import Path
import shutil
import unittest

from controller.inventory import load_inventory


class InventoryTests(unittest.TestCase):
    def test_load_example_inventory(self):
        servers = load_inventory(Path("config/servers.example.yaml"))

        self.assertEqual(len(servers), 3)
        self.assertEqual(servers[0].server_id, "openvpn-server")
        self.assertEqual(servers[0].role, "openvpn_server")
        self.assertEqual(servers[0].ssh_target, "homeops@openvpn-server.local")

    def test_rejects_unapproved_remote_health_command(self):
        payload = {
            "servers": [
                {
                    "server_id": "container-host",
                    "role": "container_host",
                    "host": "container-host.local",
                    "user": "homeops",
                    "remote_health_command": "uname -a",
                }
            ]
        }

        output_dir = Path("tests/.tmp/inventory-unsafe")
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)
        path = output_dir / "servers.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "not approved"):
            load_inventory(path)


if __name__ == "__main__":
    unittest.main()
