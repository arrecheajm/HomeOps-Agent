from pathlib import Path
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

        self.assertIn("${NTFY_AUTH_USERS:-}", compose)
        self.assertIn("${NTFY_AUTH_TOKENS:-}", compose)
        self.assertIn("NTFY_AUTH_USERS=\n", example)
        self.assertIn("NTFY_AUTH_TOKENS=\n", example)


if __name__ == "__main__":
    unittest.main()
