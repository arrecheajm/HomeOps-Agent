from pathlib import Path
import json
import shutil
import unittest
from unittest.mock import patch

from controller.collector import collect_fleet, save_fleet_health
from controller.inventory import ServerInventoryItem
from controller.ssh_client import RemoteCommandResult


class CollectorTests(unittest.TestCase):
    def test_collect_fleet_parses_successful_health_json(self):
        output_dir = Path("tests/.tmp/collector-success")
        if output_dir.exists():
            shutil.rmtree(output_dir)

        server = ServerInventoryItem(
            server_id="container-host",
            role="container_host",
            host="container-host.local",
            user="homeops",
        )
        stdout = json.dumps(
            {
                "schema_version": "1.0",
                "server_id": "container-host",
                "role": "container_host",
                "disk": [],
                "services": [],
                "updates": {},
                "docker": {"installed": True},
                "security": {},
            }
        )

        with patch(
            "controller.collector.run_remote_command",
            return_value=RemoteCommandResult(
                server_id="container-host",
                command=["ssh"],
                exit_code=0,
                stdout=stdout,
                stderr="",
                duration_seconds=0.1,
            ),
        ):
            fleet, run_dir = collect_fleet([server], output_dir)

        self.assertEqual(run_dir, output_dir)
        self.assertEqual(fleet["servers_checked"], 1)
        self.assertEqual(fleet["servers_failed"], 0)
        self.assertEqual(fleet["servers"][0]["server_id"], "container-host")
        self.assertTrue((output_dir / "raw" / "container-host.json").exists())

        fleet_path = save_fleet_health(fleet, run_dir)
        self.assertTrue(fleet_path.exists())

    def test_collect_fleet_records_nonzero_exit(self):
        output_dir = Path("tests/.tmp/collector-error")
        if output_dir.exists():
            shutil.rmtree(output_dir)

        server = ServerInventoryItem(
            server_id="openvpn-server",
            role="openvpn_server",
            host="openvpn-server.local",
            user="homeops",
        )

        with patch(
            "controller.collector.run_remote_command",
            return_value=RemoteCommandResult(
                server_id="openvpn-server",
                command=["ssh"],
                exit_code=2,
                stdout="",
                stderr="script missing",
                duration_seconds=0.1,
            ),
        ):
            fleet, _run_dir = collect_fleet([server], output_dir)

        self.assertEqual(fleet["servers_checked"], 0)
        self.assertEqual(fleet["servers_failed"], 1)
        self.assertEqual(fleet["collection_errors"][0]["server_id"], "openvpn-server")


if __name__ == "__main__":
    unittest.main()
