import unittest

from controller.inventory import ServerInventoryItem
from controller.ssh_client import build_ssh_command


class SshClientTests(unittest.TestCase):
    def test_build_ssh_command_uses_inventory_values(self):
        server = ServerInventoryItem(
            server_id="container-host",
            role="container_host",
            host="container-host.local",
            user="homeops",
            port=2222,
            connect_timeout_seconds=7,
            command_timeout_seconds=30,
            remote_health_command="/opt/homeops-agent/server-scripts/common/health_summary.sh",
        )

        command = build_ssh_command(server)

        self.assertEqual(command[0], "ssh")
        self.assertIn("2222", command)
        self.assertIn("ConnectTimeout=7", command)
        self.assertIn("homeops@container-host.local", command)
        self.assertEqual(
            command[-1], "/opt/homeops-agent/server-scripts/common/health_summary.sh"
        )

    def test_build_ssh_command_rejects_unapproved_command(self):
        server = ServerInventoryItem(
            server_id="container-host",
            role="container_host",
            host="container-host.local",
            user="homeops",
            remote_health_command="uname -a",
        )

        with self.assertRaisesRegex(ValueError, "not approved"):
            build_ssh_command(server)


if __name__ == "__main__":
    unittest.main()
