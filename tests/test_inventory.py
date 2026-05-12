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
        self.assertEqual(servers[0].access_profile, "guarded")
        self.assertFalse(servers[0].rebuildable)
        self.assertEqual(servers[1].access_profile, "experimental")
        self.assertTrue(servers[1].rebuildable)
        self.assertTrue(servers[1].allows_admin_experiments)
        self.assertEqual(servers[2].access_profile, "lab")
        self.assertTrue(servers[2].rebuildable)

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

    def test_rejects_unknown_access_profile(self):
        payload = {
            "servers": [
                {
                    "server_id": "container-host",
                    "role": "container_host",
                    "host": "container-host.local",
                    "user": "homeops",
                    "access_profile": "root-everywhere",
                }
            ]
        }

        output_dir = Path("tests/.tmp/inventory-profile")
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)
        path = output_dir / "servers.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "access_profile"):
            load_inventory(path)

    def test_rejects_guarded_rebuildable_server(self):
        payload = {
            "servers": [
                {
                    "server_id": "openvpn-server",
                    "role": "openvpn_server",
                    "host": "openvpn-server.local",
                    "user": "homeops",
                    "access_profile": "guarded",
                    "rebuildable": True,
                }
            ]
        }

        output_dir = Path("tests/.tmp/inventory-rebuildable")
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)
        path = output_dir / "servers.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "rebuildable"):
            load_inventory(path)


if __name__ == "__main__":
    unittest.main()
