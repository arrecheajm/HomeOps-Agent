from pathlib import Path
import json
import os
import shutil
import subprocess
import unittest


STACK_DIR = Path("stacks/mission-control")


class MissionControlStackTests(unittest.TestCase):
    def test_compose_pins_three_images_and_avoids_latest(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertNotIn(":latest", compose)
        self.assertIn("gethomepage/homepage:v1.13.2", compose)
        self.assertIn("louislam/uptime-kuma:2.4.0", compose)
        self.assertIn("binwiederhier/ntfy:v2.23.0", compose)
        self.assertEqual(compose.count("@sha256:"), 3)

    def test_all_ports_bind_to_the_lan_address(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertEqual(compose.count("    ports:\n"), 3)
        self.assertIn("${HOMEOPS_LAN_IP:-192.168.86.58}:8081:3000", compose)
        self.assertIn("${HOMEOPS_LAN_IP:-192.168.86.58}:3001:3001", compose)
        self.assertIn("${HOMEOPS_LAN_IP:-192.168.86.58}:8082:8080", compose)
        self.assertNotIn('"0.0.0.0:', compose)

    def test_homepage_has_no_docker_socket(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertNotIn("/var/run/docker.sock", compose)
        self.assertIn("./homepage:/app/config:ro", compose)

    def test_ntfy_denies_anonymous_access(self):
        config = (STACK_DIR / "ntfy/server.yml").read_text(encoding="utf-8")

        self.assertIn('auth-default-access: "deny-all"', config)
        self.assertIn("enable-login: true", config)
        self.assertIn('listen-http: ":8080"', config)

    def test_services_have_health_and_resource_limits(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertEqual(compose.count("    healthcheck:\n"), 3)
        self.assertEqual(compose.count("    pids_limit:"), 3)
        self.assertEqual(compose.count("    mem_limit:"), 3)
        self.assertEqual(compose.count("    cpus:"), 3)
        self.assertEqual(compose.count("        max-size: 10m"), 3)

    def test_stateful_services_run_as_their_data_owner(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn('    user: "1000:1000"', compose)
        self.assertEqual(compose.count('    user: "1000:1000"'), 2)

    def test_uptime_kuma_selects_sqlite_non_interactively(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn("      UPTIME_KUMA_DB_TYPE: sqlite", compose)

    def test_homepage_starts_with_useful_links(self):
        services = (STACK_DIR / "homepage/services.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("/d/homeops-overview", services)
        self.assertIn("Uptime Kuma", services)
        self.assertIn("Notifications", services)
        self.assertIn("Portainer", services)

    def test_secret_values_are_not_committed(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")
        example = (STACK_DIR / ".env.example").read_text(encoding="utf-8")

        self.assertNotIn("NTFY_AUTH_USERS:", compose)
        self.assertNotIn("NTFY_AUTH_TOKENS:", compose)
        self.assertIn("ntfy-runtime}:/run/secrets:ro", compose)
        self.assertNotIn("ntfy_admin_password_hash:/run/secrets", compose)
        self.assertNotIn("ntfy_service_password_hash:/run/secrets", compose)
        self.assertNotIn("ntfy_access_token:/run/secrets", compose)
        self.assertNotIn("/run/secrets/ntfy_service_password:ro", compose)
        self.assertIn("MISSION_CONTROL_NTFY_SECRET_DIR=", example)
        self.assertIn("/ntfy-runtime", example)

    def test_ntfy_loads_secrets_at_runtime(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn('IFS= read -r ntfy_admin_hash', compose)
        self.assertIn('IFS= read -r ntfy_service_hash', compose)
        self.assertIn('IFS= read -r ntfy_token', compose)
        self.assertEqual(compose.count('|| test -n "$${ntfy_'), 3)
        self.assertIn('admin:$${ntfy_admin_hash}:admin', compose)
        self.assertIn('homeops:$${ntfy_service_hash}:user', compose)
        self.assertIn('homeops:homeops-alerts:rw', compose)
        self.assertIn('homeops:$${ntfy_token}:HomeOps', compose)
        self.assertIn("exec ntfy serve", compose)

    def test_uptime_kuma_bootstrap_is_pinned_and_idempotent(self):
        compose = (STACK_DIR / "compose.yaml").read_text(encoding="utf-8")
        bootstrap = (STACK_DIR / "uptime-kuma/bootstrap.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("./uptime-kuma/bootstrap.js:/app/homeops-bootstrap.js:ro", compose)
        self.assertIn("./uptime-kuma/bootstrap-contract.js:/app/bootstrap-contract.js:ro", compose)
        self.assertIn('const ADMIN_USER = "admin"', bootstrap)
        self.assertIn('const STATUS_PAGE_SLUG = "homeops"', bootstrap)
        self.assertIn('emitAck("needSetup")', bootstrap)
        self.assertIn("socket.emit(event, ...args", bootstrap)
        self.assertNotIn("socket.timeout(TIMEOUT_MS).emit", bootstrap)
        self.assertIn('emitAck("setup", ADMIN_USER, password)', bootstrap)
        self.assertIn('emitAck("login"', bootstrap)
        self.assertIn('"addNotification"', bootstrap)
        self.assertIn('emitAck("add", monitorPayload(spec, notificationID))', bootstrap)
        self.assertIn('emitAck("editMonitor"', bootstrap)
        self.assertIn('emitAck("addStatusPage"', bootstrap)
        self.assertIn('"saveStatusPage"', bootstrap)
        self.assertIn("Existing monitor", bootstrap)
        self.assertIn("uptime_kuma_bootstrap_verified", bootstrap)
        self.assertNotIn("process.argv", bootstrap)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for JS contract tests")
    def test_uptime_kuma_contract_handles_real_collection_shapes(self):
        contract_path = (STACK_DIR / "uptime-kuma/bootstrap-contract.js").resolve()
        script = f"""
const contract = require({json.dumps(str(contract_path))});
const token = "tk_" + "a".repeat(29);
const input = contract.parseBootstrapInput(JSON.stringify({{
    uptimeKumaAdminPassword: "correct-horse-battery-staple",
    ntfyAccessToken: token,
}}));
if (input.ntfyAccessToken !== token) process.exit(1);
const page = contract.findStatusPage({{ 7: {{ id: 7, slug: "homeops" }} }}, "homeops");
if (!page || page.id !== 7) process.exit(2);
const notification = contract.ntfyNotificationPayload(token);
if (notification.type !== "ntfy" || notification.ntfytopic !== "homeops-alerts") process.exit(3);
if (contract.notificationType({{ config: JSON.stringify(notification) }}) !== "ntfy") process.exit(4);
const ids = contract.withNotification({{ 3: true }}, 9);
if (!ids[3] || !ids[9]) process.exit(5);
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for JS contract tests")
    def test_uptime_kuma_bootstrap_provisions_scoped_alerts(self):
        bootstrap_path = (STACK_DIR / "uptime-kuma/bootstrap.js").resolve()
        node_modules = Path(
            "tests/fixtures/uptime-kuma-node-modules"
        ).resolve()
        token = "tk_" + ("a" * 29)
        bootstrap_input = json.dumps(
            {
                "uptimeKumaAdminPassword": "correct-horse-battery-staple",
                "ntfyAccessToken": token,
            }
        )
        environment = os.environ.copy()
        environment["NODE_PATH"] = str(node_modules)
        result = subprocess.run(
            [shutil.which("node"), str(bootstrap_path)],
            input=bootstrap_input,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("uptime_kuma_bootstrap_verified", result.stdout)


if __name__ == "__main__":
    unittest.main()
