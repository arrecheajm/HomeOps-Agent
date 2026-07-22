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
        self.assertEqual(record["command"][-1], "docker restart watchtower")
        self.assertIn("Approve action restart_docker_container", record["expected_approval"])

    def test_inspect_storage_devices_executes_without_approval(self):
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="storage metadata\n",
            stderr="",
        )

        with patch(
            "controller.action_runner.subprocess.run",
            side_effect=[completed, completed],
        ) as subprocess_run:
            attempt = run_action(
                "inspect_storage_devices",
                "container-host",
                [self._container_server()],
                {},
                actions_dir=self.actions_dir,
            )

        self.assertEqual(attempt.record["status"], "completed")
        self.assertEqual(attempt.record["approval_source"], "not_required")
        self.assertEqual(subprocess_run.call_count, 2)
        rendered = "\n".join(
            command[-1] for command in attempt.record["commands"]
        )
        self.assertIn(
            "mountpoint -q /srv/homeops-storage",
            attempt.record["commands"][0][-1],
        )
        self.assertIn("lsblk --json --bytes --output", rendered)
        self.assertIn("/srv/homeops-storage/.homeops-storage", rendered)
        self.assertNotIn("mkfs", rendered)
        self.assertNotIn("mount /", rendered)

    def test_inspect_storage_devices_rejects_arguments(self):
        with self.assertRaisesRegex(ActionError, "does not accept arguments"):
            run_action(
                "inspect_storage_devices",
                "container-host",
                [self._container_server()],
                {"path": "/tmp"},
                actions_dir=self.actions_dir,
            )

    def test_inspect_docker_container_dry_run_writes_status_log_and_config_commands(self):
        attempt = run_action(
            "inspect_docker_container",
            "container-host",
            [self._container_server()],
            {"container": "watchtower"},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 3)
        self.assertEqual(
            record["commands"][0][-1],
            "docker ps -a --filter name=watchtower",
        )
        self.assertEqual(
            record["commands"][1][-1],
            "docker logs --tail 120 watchtower",
        )
        self.assertIn("docker inspect --format", record["commands"][2][-1])
        self.assertIn("image={{.Config.Image}}", record["commands"][2][-1])
        self.assertIn("Approve action inspect_docker_container", record["expected_approval"])

    def test_inspect_docker_container_executes_sequence_after_approval(self):
        args = {"container": "watchtower"}
        approval = approvals.approval_phrase(
            "inspect_docker_container",
            "container-host",
            args,
        )
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="watchtower\n",
            stderr="",
        )

        with patch(
            "controller.action_runner.subprocess.run",
            side_effect=[completed, completed, completed],
        ) as subprocess_run:
            attempt = run_action(
                "inspect_docker_container",
                "container-host",
                [self._container_server()],
                args,
                approval_text=approval,
                actions_dir=self.actions_dir,
            )

        self.assertEqual(attempt.record["status"], "completed")
        self.assertEqual(attempt.record["exit_code"], 0)
        self.assertEqual(subprocess_run.call_count, 3)

    def test_replace_watchtower_container_dry_run_writes_recreate_commands(self):
        attempt = run_action(
            "replace_watchtower_container",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 4)
        self.assertEqual(record["commands"][0][-1], "docker pull containrrr/watchtower")
        self.assertEqual(record["commands"][1][-1], "docker stop watchtower")
        self.assertEqual(record["commands"][2][-1], "docker rm watchtower")
        self.assertIn("docker run -d --name watchtower", record["commands"][3][-1])
        self.assertIn("--label-enable --cleanup", record["commands"][3][-1])

    def test_replace_watchtower_container_executes_after_approval(self):
        approval = approvals.approval_phrase(
            "replace_watchtower_container",
            "container-host",
            {},
        )
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="ok\n",
            stderr="",
        )

        with patch(
            "controller.action_runner.subprocess.run",
            side_effect=[completed, completed, completed, completed],
        ) as subprocess_run:
            attempt = run_action(
                "replace_watchtower_container",
                "container-host",
                [self._container_server()],
                {},
                approval_text=approval,
                actions_dir=self.actions_dir,
            )

        self.assertEqual(attempt.record["status"], "completed")
        self.assertEqual(attempt.record["exit_code"], 0)
        self.assertEqual(subprocess_run.call_count, 4)

    def test_retire_disposable_containers_dry_run_is_exactly_bounded(self):
        attempt = run_action(
            "retire_disposable_containers",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 4)
        self.assertIn("filebrowser/filebrowser:latest", record["commands"][0][-1])
        self.assertEqual(
            record["commands"][1][-1],
            "docker rm --force --volumes -- filebrowser mysql57 nonprofit-postgres",
        )
        self.assertEqual(
            record["commands"][2][-1],
            "docker volume rm -- dashboards_filebrowser_data dev-db_mysql_data nonprofit_postgres_data",
        )
        self.assertEqual(
            record["expected_approval"],
            "Approve action retire_disposable_containers on container-host",
        )

    def test_retire_disposable_containers_rejects_arguments(self):
        with self.assertRaisesRegex(ActionError, "does not accept arguments"):
            run_action(
                "retire_disposable_containers",
                "container-host",
                [self._container_server()],
                {"container": "anything"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_retire_disposable_containers_executes_after_exact_approval(self):
        approval = approvals.approval_phrase(
            "retire_disposable_containers",
            "container-host",
            {},
        )
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="ok\n",
            stderr="",
        )

        with patch(
            "controller.action_runner.subprocess.run",
            side_effect=[completed, completed, completed, completed],
        ) as subprocess_run:
            attempt = run_action(
                "retire_disposable_containers",
                "container-host",
                [self._container_server()],
                {},
                approval_text=approval,
                actions_dir=self.actions_dir,
            )

        self.assertEqual(attempt.record["status"], "completed")
        self.assertEqual(subprocess_run.call_count, 4)

    def test_preflight_monitoring_images_dry_run_is_non_disruptive_and_pinned(self):
        attempt = run_action(
            "preflight_monitoring_images",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        rendered = "\n".join(command[-1] for command in record["commands"])

        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(rendered.count("docker pull"), 4)
        self.assertGreaterEqual(rendered.count("@sha256:"), 8)
        self.assertIn("/bin/promtool", rendered)
        self.assertNotIn("docker stop", rendered)
        self.assertNotIn("docker restart", rendered)
        self.assertNotIn("docker compose up", rendered)
        self.assertEqual(
            record["expected_approval"],
            "Approve action preflight_monitoring_images on container-host",
        )

    def test_preflight_mission_control_images_is_bounded_and_non_disruptive(self):
        attempt = run_action(
            "preflight_mission_control_images",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        rendered = "\n".join(command[-1] for command in record["commands"])

        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 7)
        self.assertEqual(rendered.count("docker pull"), 3)
        self.assertGreaterEqual(rendered.count("@sha256:"), 9)
        self.assertEqual(rendered.count("--entrypoint node"), 2)
        self.assertEqual(rendered.count(" --version"), 2)
        self.assertIn("command -v ntfy", rendered)
        self.assertIn("homeops-mission-control-homepage-1", rendered)
        self.assertIn("homeops-mission-control_ntfy-data", rendered)
        self.assertIn("grep -Eq", rendered)
        self.assertNotIn("docker compose up", rendered)
        self.assertNotIn("docker stop", rendered)
        self.assertNotIn("docker rm --force", rendered)
        self.assertEqual(
            record["expected_approval"],
            "Approve action preflight_mission_control_images on container-host",
        )

    def test_preflight_mission_control_images_rejects_arguments(self):
        with self.assertRaisesRegex(ActionError, "does not accept arguments"):
            run_action(
                "preflight_mission_control_images",
                "container-host",
                [self._container_server()],
                {"image": "anything"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_provision_mission_control_secrets_is_bounded_and_redacted(self):
        attempt = run_action(
            "provision_mission_control_secrets",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        rendered = "\n".join(command[-1] for command in record["commands"])

        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 4)
        self.assertEqual(sum(command[0] == "scp" for command in record["commands"]), 3)
        self.assertIn("secrets.token_urlsafe(32)", rendered)
        self.assertIn("tk_", rendered)
        self.assertIn("bcryptjs", rendered)
        self.assertIn("ntfy_password_hash", rendered)
        self.assertIn("stat -c %a", rendered)
        self.assertIn("test ! -L", rendered)
        self.assertIn("--read-only", rendered)
        self.assertNotIn("cat ", rendered)
        self.assertNotIn("NTFY_AUTH_USERS=", rendered)
        self.assertNotIn("NTFY_AUTH_TOKENS=", rendered)
        self.assertTrue(record["commands"][1][-1].endswith("uptime_kuma_admin_password"))
        self.assertTrue(record["commands"][2][-1].endswith("ntfy_admin_password"))
        self.assertTrue(record["commands"][3][-1].endswith("ntfy_access_token"))
        self.assertEqual(
            record["expected_approval"],
            "Approve action provision_mission_control_secrets on container-host",
        )

    def test_provision_mission_control_secrets_rejects_arguments(self):
        with self.assertRaisesRegex(ActionError, "does not accept arguments"):
            run_action(
                "provision_mission_control_secrets",
                "container-host",
                [self._container_server()],
                {"password": "must-not-be-accepted"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_deploy_monitoring_stack_dry_run_is_bounded_and_recoverable(self):
        attempt = run_action(
            "deploy_monitoring_stack",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        rendered = "\n".join(command[-1] for command in record["commands"])

        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 12)
        self.assertEqual(record["commands"][0][0], "ssh")
        self.assertNotIn("\\home\\", record["commands"][0][-1])
        self.assertEqual(
            sum(command[0] == "scp" for command in record["commands"]),
            8,
        )
        self.assertIn("grafana_admin_password", rendered)
        self.assertIn("stat -c %a", rendered)
        self.assertIn("sha256sum", rendered)
        self.assertIn("docker compose", rendered)
        self.assertIn("up -d --wait --wait-timeout 180", rendered)
        self.assertIn("reset-admin-password --password-from-stdin", rendered)
        self.assertIn("HOMEOPS_LAN_IP=127.0.0.1", rendered)
        self.assertIn("admin:admin", rendered)
        self.assertNotIn("cat /run/secrets/grafana_admin_password", rendered)
        self.assertIn("docker start -- cadvisor", rendered)
        self.assertGreaterEqual(rendered.count("trap"), 4)
        self.assertIn("192.168.86.58:3000", rendered)
        self.assertNotIn("docker volume rm", rendered)
        self.assertNotIn("monitoring_grafana-data monitoring_prometheus-data", rendered)
        self.assertEqual(
            record["expected_approval"],
            "Approve action deploy_monitoring_stack on container-host",
        )

    def test_provision_monitoring_secret_dry_run_never_prints_secret_value(self):
        attempt = run_action(
            "provision_monitoring_secret",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        generation = record["commands"][0][-1]
        recovery = record["commands"][1]

        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 2)
        self.assertIn("secrets.token_urlsafe(32)", generation)
        self.assertIn('> "$tmp"', generation)
        self.assertIn("test ! -L", generation)
        self.assertIn("stat -c %a", generation)
        self.assertNotIn("cat ", generation)
        self.assertEqual(recovery[0], "scp")
        self.assertTrue(recovery[-1].endswith("grafana_admin_password"))
        self.assertEqual(
            record["expected_approval"],
            "Approve action provision_monitoring_secret on container-host",
        )

    def test_provision_monitoring_secret_rejects_arguments(self):
        with self.assertRaisesRegex(ActionError, "does not accept arguments"):
            run_action(
                "provision_monitoring_secret",
                "container-host",
                [self._container_server()],
                {"password": "must-not-be-accepted"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_deploy_monitoring_stack_rejects_arguments(self):
        with self.assertRaisesRegex(ActionError, "does not accept arguments"):
            run_action(
                "deploy_monitoring_stack",
                "container-host",
                [self._container_server()],
                {"project": "anything"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_repair_monitoring_grafana_dry_run_is_bounded_and_recoverable(self):
        attempt = run_action(
            "repair_monitoring_grafana",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        rendered = "\n".join(command[-1] for command in record["commands"])

        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 12)
        self.assertEqual(
            sum(command[0] == "scp" for command in record["commands"]),
            8,
        )
        self.assertIn("compose.candidate.yaml", rendered)
        self.assertIn("compose.pre-repair.yaml", rendered)
        self.assertIn("reset-admin-password --password-from-stdin", rendered)
        self.assertIn("GF_PLUGINS_PREINSTALL_DISABLED", rendered)
        self.assertIn("GF_PLUGINS_PREINSTALL_AUTO_UPDATE", rendered)
        self.assertIn("Failed to install plugin", rendered)
        self.assertIn("HOMEOPS_LAN_IP=127.0.0.1", rendered)
        self.assertIn("admin:admin", rendered)
        self.assertNotIn("cat /run/secrets/grafana_admin_password", rendered)
        self.assertIn("grafana_admin_password: Permission denied", rendered)
        self.assertNotIn("docker stop -- cadvisor", rendered)
        self.assertNotIn("docker volume rm", rendered)
        self.assertEqual(
            record["expected_approval"],
            "Approve action repair_monitoring_grafana on container-host",
        )

    def test_repair_monitoring_grafana_rejects_arguments(self):
        with self.assertRaisesRegex(ActionError, "does not accept arguments"):
            run_action(
                "repair_monitoring_grafana",
                "container-host",
                [self._container_server()],
                {"container": "anything"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_rollback_monitoring_stack_dry_run_restores_only_fixed_old_stack(self):
        attempt = run_action(
            "rollback_monitoring_stack",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        rendered = "\n".join(command[-1] for command in record["commands"])

        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 3)
        self.assertIn("docker compose", rendered)
        self.assertIn("docker start -- cadvisor", rendered)
        self.assertIn("down --volumes", rendered)
        self.assertIn("homeops-monitoring_grafana-data", rendered)
        self.assertNotIn("docker system prune", rendered)
        self.assertNotIn("monitoring_grafana-data monitoring_prometheus-data", rendered)
        self.assertEqual(
            record["expected_approval"],
            "Approve action rollback_monitoring_stack on container-host",
        )

    def test_rollback_monitoring_stack_rejects_arguments(self):
        with self.assertRaisesRegex(ActionError, "does not accept arguments"):
            run_action(
                "rollback_monitoring_stack",
                "container-host",
                [self._container_server()],
                {"volume": "anything"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_retire_legacy_monitoring_stack_is_exactly_bounded(self):
        attempt = run_action(
            "retire_legacy_monitoring_stack",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        rendered = "\n".join(command[-1] for command in record["commands"])

        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 3)
        self.assertIn(
            "docker rm -- cadvisor monitoring-grafana-1 "
            "monitoring-node_exporter-1 monitoring-prometheus-1",
            rendered,
        )
        self.assertIn(
            "docker volume rm -- monitoring_grafana-data "
            "monitoring_prometheus-data",
            rendered,
        )
        self.assertNotIn("docker system prune", rendered)
        self.assertNotIn(
            "docker volume rm -- homeops-monitoring_grafana-data",
            rendered,
        )
        self.assertIn("admin:admin", rendered)
        self.assertEqual(
            record["expected_approval"],
            "Approve action retire_legacy_monitoring_stack on container-host",
        )

    def test_retire_legacy_monitoring_stack_rejects_arguments(self):
        with self.assertRaisesRegex(ActionError, "does not accept arguments"):
            run_action(
                "retire_legacy_monitoring_stack",
                "container-host",
                [self._container_server()],
                {"container": "anything"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_retire_legacy_monitoring_files_is_exactly_bounded(self):
        attempt = run_action(
            "retire_legacy_monitoring_files",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        rendered = "\n".join(command[-1] for command in record["commands"])

        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 3)
        self.assertIn(
            "rm -- docker-compose.yml prometheus.yml readme.md",
            rendered,
        )
        self.assertIn(
            "rmdir -- /home/containerserver/docker_lab/monitoring",
            rendered,
        )
        self.assertIn("find . -xdev -mindepth 1 -maxdepth 1", rendered)
        self.assertNotIn("rm -rf", rendered)
        self.assertNotIn("/home/containerserver/docker_lab/dev-db", rendered)
        self.assertEqual(
            record["expected_approval"],
            "Approve action retire_legacy_monitoring_files on container-host",
        )

    def test_retire_legacy_monitoring_files_rejects_arguments(self):
        with self.assertRaisesRegex(ActionError, "does not accept arguments"):
            run_action(
                "retire_legacy_monitoring_files",
                "container-host",
                [self._container_server()],
                {"path": "anything"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_migrate_watchtower_container_dry_run_uses_maintained_image(self):
        attempt = run_action(
            "migrate_watchtower_container",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 4)
        self.assertEqual(record["commands"][0][-1], "docker pull nickfedor/watchtower")
        self.assertIn("docker run -d --name watchtower", record["commands"][3][-1])
        self.assertIn("nickfedor/watchtower", record["commands"][3][-1])
        self.assertEqual(
            record["expected_approval"],
            "Approve action migrate_watchtower_container on container-host",
        )

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
            record["command"][-1],
            "sudo -n systemctl restart -- AgentDVR.service",
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

        self.assertEqual(
            attempt.record["command"][-1],
            "sudo -n systemctl restart -- openvpnas.service",
        )

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
        self.assertEqual(
            record["commands"][1][-1],
            "chmod 755 /opt/homeops-agent/server-scripts/common/health_summary.sh",
        )
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

    def test_deploy_sudoers_profile_dry_run_writes_lab_profile_command(self):
        attempt = run_action(
            "deploy_sudoers_profile",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(
            record["expected_approval"],
            "Approve action deploy_sudoers_profile on container-host",
        )
        command = record["command"][-1]
        self.assertIn("homeops ALL=(root) NOPASSWD: ALL", command)
        self.assertIn("/etc/sudoers.d/homeops-agent", command)
        self.assertIn("/usr/sbin/visudo -cf", command)
        self.assertIn("/usr/bin/install -o root -g root -m 0440", command)

    def test_deploy_sudoers_profile_dry_run_writes_experimental_profile(self):
        attempt = run_action(
            "deploy_sudoers_profile",
            "ispy-server",
            [self._ispy_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(
            record["expected_approval"],
            "Approve action deploy_sudoers_profile on ispy-server",
        )
        command = record["command"][-1]
        self.assertIn("homeops ALL=(root) NOPASSWD: /usr/bin/unattended-upgrade", command)
        self.assertIn("AgentDVR.service", command)
        self.assertIn("/usr/bin/bash -lc *", command)
        self.assertIn("experimental.sudoers.template", command)

    def test_deploy_sudoers_profile_rejects_unsafe_user(self):
        with self.assertRaisesRegex(ActionError, "not safe for sudoers"):
            run_action(
                "deploy_sudoers_profile",
                "ispy-server",
                [
                    ServerInventoryItem(
                        server_id="ispy-server",
                        role="ispy_server",
                        host="ispy-server.local",
                        user="homeops ALL=(root) NOPASSWD: ALL",
                        identity_file="~/.ssh/homeops_ed25519",
                        access_profile="experimental",
                        rebuildable=True,
                    )
                ],
                {},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_reboot_server_dry_run_writes_delayed_shutdown_command(self):
        attempt = run_action(
            "reboot_server",
            "ispy-server",
            [self._ispy_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(record["arguments"], {})
        self.assertEqual(
            record["command"][-1],
            "sudo -n shutdown -r +1 HomeOps-approved-reboot",
        )
        self.assertEqual(
            record["expected_approval"],
            "Approve action reboot_server on ispy-server",
        )

    def test_reboot_server_executes_after_approval(self):
        args = {}
        approval = approvals.approval_phrase("reboot_server", "ispy-server", args)
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="Reboot scheduled\n",
            stderr="",
        )

        with patch("controller.action_runner.subprocess.run", return_value=completed):
            attempt = run_action(
                "reboot_server",
                "ispy-server",
                [self._ispy_server()],
                args,
                approval_text=approval,
                actions_dir=self.actions_dir,
            )

        self.assertEqual(attempt.record["status"], "completed")
        self.assertEqual(attempt.record["exit_code"], 0)
        self.assertEqual(attempt.record["stdout"], "Reboot scheduled")

    def test_apply_security_updates_dry_run_uses_unattended_upgrade(self):
        attempt = run_action(
            "apply_security_updates",
            "openvpn-server",
            [self._openvpn_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(record["arguments"], {})
        self.assertEqual(
            record["command"][-1],
            "sudo -n unattended-upgrade",
        )
        self.assertEqual(
            record["expected_approval"],
            "Approve action apply_security_updates on openvpn-server",
        )

    def test_apply_security_updates_executes_after_approval(self):
        args = {}
        approval = approvals.approval_phrase(
            "apply_security_updates", "openvpn-server", args
        )
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="Packages upgraded\n",
            stderr="",
        )

        with patch("controller.action_runner.subprocess.run", return_value=completed):
            attempt = run_action(
                "apply_security_updates",
                "openvpn-server",
                [self._openvpn_server()],
                args,
                approval_text=approval,
                actions_dir=self.actions_dir,
            )

        self.assertEqual(attempt.record["status"], "completed")
        self.assertEqual(attempt.record["exit_code"], 0)
        self.assertEqual(attempt.record["stdout"], "Packages upgraded")

    def test_apply_package_updates_dry_run_uses_apt_upgrade_on_lab_host(self):
        attempt = run_action(
            "apply_package_updates",
            "container-host",
            [self._container_server()],
            {},
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(len(record["commands"]), 2)
        self.assertEqual(record["commands"][0][-1], "sudo -n apt-get update")
        self.assertEqual(
            record["commands"][1][-1],
            "sudo -n env DEBIAN_FRONTEND=noninteractive apt-get -y upgrade",
        )
        self.assertEqual(
            record["expected_approval"],
            "Approve action apply_package_updates on container-host",
        )

    def test_apply_package_updates_executes_after_approval(self):
        args = {}
        approval = approvals.approval_phrase(
            "apply_package_updates", "container-host", args
        )
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="Packages upgraded\n",
            stderr="",
        )

        with patch(
            "controller.action_runner.subprocess.run",
            side_effect=[completed, completed],
        ) as subprocess_run:
            attempt = run_action(
                "apply_package_updates",
                "container-host",
                [self._container_server()],
                args,
                approval_text=approval,
                actions_dir=self.actions_dir,
            )

        self.assertEqual(attempt.record["status"], "completed")
        self.assertEqual(attempt.record["exit_code"], 0)
        self.assertEqual(subprocess_run.call_count, 2)

    def test_apply_package_updates_rejects_non_container_host(self):
        with self.assertRaisesRegex(ActionError, "not allowed for role openvpn_server"):
            run_action(
                "apply_package_updates",
                "openvpn-server",
                [self._openvpn_server()],
                {},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_run_admin_command_dry_run_writes_logged_command(self):
        args = {
            "command": "apt-get update",
            "intent": "refresh package metadata",
        }

        attempt = run_action(
            "run_admin_command",
            "ispy-server",
            [self._ispy_server()],
            args,
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        record = json.loads(attempt.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "dry_run")
        self.assertEqual(record["access_profile"], "experimental")
        self.assertTrue(record["rebuildable"])
        self.assertEqual(record["arguments"], args)
        self.assertEqual(
            record["command"][-1],
            "sudo -n /usr/bin/bash -lc 'apt-get update'",
        )
        self.assertEqual(
            record["expected_approval"],
            "Approve action run_admin_command on ispy-server "
            "with command apt-get update, intent refresh package metadata",
        )

    def test_run_admin_command_executes_after_approval(self):
        args = {
            "command": "systemctl status AgentDVR.service",
            "intent": "inspect camera service status",
        }
        approval = approvals.approval_phrase(
            "run_admin_command",
            "ispy-server",
            args,
        )
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="active\n",
            stderr="",
        )

        with patch("controller.action_runner.subprocess.run", return_value=completed):
            attempt = run_action(
                "run_admin_command",
                "ispy-server",
                [self._ispy_server()],
                args,
                approval_text=approval,
                actions_dir=self.actions_dir,
            )

        self.assertEqual(attempt.record["status"], "completed")
        self.assertEqual(attempt.record["exit_code"], 0)
        self.assertEqual(attempt.record["stdout"], "active")

    def test_run_admin_command_rejects_guarded_server(self):
        with self.assertRaisesRegex(ActionError, "experimental or lab access profiles"):
            run_action(
                "run_admin_command",
                "openvpn-server",
                [self._openvpn_server()],
                {
                    "command": "apt-get update",
                    "intent": "refresh package metadata",
                },
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_run_admin_command_requires_intent(self):
        with self.assertRaisesRegex(ActionError, "intent is required"):
            run_action(
                "run_admin_command",
                "container-host",
                [self._container_server()],
                {"command": "docker ps"},
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_run_admin_command_rejects_forbidden_policy_pattern_on_experimental(self):
        with self.assertRaisesRegex(ActionError, "forbidden policy pattern"):
            run_action(
                "run_admin_command",
                "ispy-server",
                [self._ispy_server()],
                {
                    "command": "rm -rf /tmp/example",
                    "intent": "exercise forbidden policy",
                },
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_run_admin_command_rejects_destructive_disk_pattern_on_experimental(self):
        with self.assertRaisesRegex(ActionError, "forbidden policy pattern"):
            run_action(
                "run_admin_command",
                "ispy-server",
                [self._ispy_server()],
                {
                    "command": "mkfs.ext4 /dev/sda1",
                    "intent": "exercise rebuild guardrail",
                },
                dry_run=True,
                actions_dir=self.actions_dir,
            )

    def test_run_admin_command_allows_full_sudo_pattern_on_lab(self):
        attempt = run_action(
            "run_admin_command",
            "container-host",
            [self._container_server()],
            {
                "command": "apt-get install -y htop",
                "intent": "install package in Codex lab",
            },
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        self.assertEqual(attempt.record["status"], "dry_run")
        self.assertEqual(attempt.record["access_profile"], "lab")
        self.assertEqual(
            attempt.record["command"][-1],
            "sudo -n /usr/bin/bash -lc 'apt-get install -y htop'",
        )

    def test_run_admin_command_allows_destructive_pattern_on_lab(self):
        attempt = run_action(
            "run_admin_command",
            "container-host",
            [self._container_server()],
            {
                "command": "mkfs.ext4 /dev/sda1",
                "intent": "exercise full lab sudo authority",
            },
            dry_run=True,
            actions_dir=self.actions_dir,
        )

        self.assertEqual(attempt.record["status"], "dry_run")
        self.assertEqual(attempt.record["access_profile"], "lab")
        self.assertIn("mkfs.ext4", attempt.record["command"][-1])

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
            access_profile="lab",
            rebuildable=True,
        )

    def _ispy_server(self) -> ServerInventoryItem:
        return ServerInventoryItem(
            server_id="ispy-server",
            role="ispy_server",
            host="ispy-server.local",
            user="homeops",
            identity_file="~/.ssh/homeops_ed25519",
            access_profile="experimental",
            rebuildable=True,
        )

    def _openvpn_server(self) -> ServerInventoryItem:
        return ServerInventoryItem(
            server_id="openvpn-server",
            role="openvpn_server",
            host="openvpn-server.local",
            user="homeops",
            identity_file="~/.ssh/homeops_ed25519",
            access_profile="guarded",
            rebuildable=False,
        )


if __name__ == "__main__":
    unittest.main()
