from pathlib import Path
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch

from controller import approvals
from controller.action_runner import ActionError, run_action
from controller.inventory import ServerInventoryItem


class ActionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.actions_dir = Path("tests/.tmp/action-history")
        if self.actions_dir.exists():
            shutil.rmtree(self.actions_dir)
        self.actions_dir.mkdir(parents=True)

    def test_restart_docker_container_dry_run_writes_history(self):
        attempt = run_action(
            "restart_docker_container",
            "container-host",
            [self._container_server()],
            {"container": "watchtower"},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        self.assertTrue(attempt.record_path.exists())
        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(record["exit_code"], None)
        self.assertEqual(record["arguments"], {"container": "watchtower"})
        self.assertEqual(record["command"][-3:], ["docker", "restart", "watchtower"])
        self.assertIn("Approve action restart_docker_container", record["expected_approval"])

    def test_restart_docker_container_requires_exact_approval(self):
        with self.assertRaisesRegex(ActionError, "requires exact approval"):
            run_action(
                "restart_docker_container",
                "container-host",
                [self._container_server()],
                {"container": "watchtower"},
                actions_dir=self.actions_dir,
            )

        records = list(self.actions_dir.glob("*.json"))
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "denied")
        self.assertEqual(record["approval_source"], "missing_or_invalid")

    def test_restart_docker_container_executes_after_approval(self):
        args = {"container": "watchtower"}
        approval = approvals.approval_phrase(
            "restart_docker_container", "container-host", args
        )
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="watchtower\n",
            stderr="",
        )

        with patch("controller.action_runner.subprocess.run", return_value=completed):
            attempt = run_action(
                "restart_docker_container",
                "container-host",
                [self._container_server()],
                args,
                approval_text=approval,
                actions_dir=self.actions_dir,
            )

        self.assertEqual(attempt.record["status"], "completed")
        self.assertEqual(attempt.record["exit_code"], 0)
        self.assertEqual(attempt.record["stdout"], "watchtower")

    def test_restart_docker_container_rejects_unsafe_container_name(self):
        with self.assertRaisesRegex(ActionError, "Container name is required"):
            run_action(
                "restart_docker_container",
                "container-host",
                [self._container_server()],
                {"container": "watchtower;rm"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_restart_service_dry_run_writes_history(self):
        attempt = run_action(
            "restart_service",
            "ispy-server",
            [self._ispy_server()],
            {"service": "AgentDVR.service"},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(record["arguments"], {"service": "AgentDVR.service"})
        self.assertEqual(
            record["command"][-6:],
            ["sudo", "-n", "systemctl", "restart", "--", "AgentDVR.service"],
        )
        self.assertIn("Approve action restart_service", record["expected_approval"])

    def test_restart_service_normalizes_openvpnas_unit_name(self):
        attempt = run_action(
            "restart_service",
            "openvpn-server",
            [self._openvpn_server()],
            {"service": "openvpnas"},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        self.assertEqual(attempt.record["command"][-1], "openvpnas.service")

    def test_restart_service_rejects_unapproved_service_name(self):
        with self.assertRaisesRegex(ActionError, "not approved for restart"):
            run_action(
                "restart_service",
                "ispy-server",
                [self._ispy_server()],
                {"service": "ssh"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_deploy_health_script_dry_run_writes_command_sequence(self):
        attempt = run_action(
            "deploy_health_script",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(record["arguments"], {})
        self.assertEqual(len(record["commands"]), 2)
        self.assertEqual(record["commands"][0][0], "scp")
        self.assertIn("health_summary.sh", record["commands"][0][-2])
        self.assertEqual(record["commands"][1][-3:], ["chmod", "755", "/opt/homeops-agent/server-scripts/common/health_summary.sh"])
        self.assertIn("Approve action deploy_health_script", record["expected_approval"])

    def test_deploy_health_script_executes_sequence_after_approval(self):
        args = {}
        approval = approvals.approval_phrase(
            "deploy_health_script", "container-host", args
        )
        completed = subprocess.CompletedProcess(
            args=["scp"],
            returncode=0,
            stdout="",
            stderr="",
        )

        with patch(
            "controller.action_runner.subprocess.run",
            side_effect=[completed, completed],
        ) as subprocess_run:
            attempt = run_action(
                "deploy_health_script",
                "container-host",
                [self._container_server()],
                args,
                approval_text=approval,
                actions_dir=self.actions_dir,
            )

        self.assertEqual(attempt.record["status"], "completed")
        self.assertEqual(attempt.record["exit_code"], 0)
        self.assertEqual(subprocess_run.call_count, 2)

    def test_action_role_restriction_is_enforced(self):
        with self.assertRaisesRegex(ActionError, "not allowed for role"):
            run_action(
                "restart_docker_container",
                "openvpn-server",
                [
                    ServerInventoryItem(
                        server_id="openvpn-server",
                        role="openvpn_server",
                        host="openvpn-server.local",
                        user="homeops",
                    )
                ],
                {"container": "watchtower"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def _container_server(self) -> ServerInventoryItem:
        return ServerInventoryItem(
            server_id="container-host",
            role="container_host",
            host="container-host.local",
            user="homeops",
            identity_file="~/.ssh/homeops_ed25519",
        )

    def _ispy_server(self) -> ServerInventoryItem:
        return ServerInventoryItem(
            server_id="ispy-server",
            role="ispy_server",
            host="ispy-server.local",
            user="homeops",
            identity_file="~/.ssh/homeops_ed25519",
        )

    def _openvpn_server(self) -> ServerInventoryItem:
        return ServerInventoryItem(
            server_id="openvpn-server",
            role="openvpn_server",
            host="openvpn-server.local",
            user="homeops",
            identity_file="~/.ssh/homeops_ed25519",
        )


if __name__ == "__main__":
    unittest.main()
