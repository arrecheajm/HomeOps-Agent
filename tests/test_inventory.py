from pathlib import Path
import unittest

from controller.inventory import load_inventory


class InventoryTests(unittest.TestCase):
    def test_load_example_inventory(self):
        servers = load_inventory(Path("config/servers.example.yaml"))

        self.assertEqual(len(servers), 3)
        self.assertEqual(servers[0].server_id, "openvpn-server")
        self.assertEqual(servers[0].role, "openvpn_server")
        self.assertEqual(servers[0].ssh_target, "homeops@openvpn-server.local")


if __name__ == "__main__":
    unittest.main()
