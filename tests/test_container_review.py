from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import unittest
from unittest.mock import patch

from controller.container_review import (
    build_container_review,
    render_container_review,
    write_container_review,
)
from controller.history import ActionSummary, RunSummary


class ContainerReviewTests(unittest.TestCase):
    def test_build_container_review_recommends_container_diagnosis_and_reboot(self):
        review = build_container_review(
            self._run_summary(),
            "container-host",
            [self._action_summary()],
            generated_at="2026-05-26T18:00:00Z",
        )

        titles = [item["title"] for item in review["recommendations"]]
        self.assertIn("Inspect watchtower restart loop", titles)
        self.assertIn(
            "Restart watchtower if logs show a transient failure",
            titles,
        )
        self.assertIn("Apply pending package updates", titles)
        self.assertIn("Plan a container host reboot", titles)
        commands = [
            item["dry_run_command"]
            for item in review["recommendations"]
            if item.get("dry_run_command")
        ]
        self.assertTrue(any("inspect_docker_container" in item for item in commands))
        self.assertTrue(any("restart_docker_container" in item for item in commands))
        self.assertTrue(any("apply_package_updates" in item for item in commands))
        self.assertTrue(any("reboot_server" in item for item in commands))

    def test_build_container_review_reports_collection_failure(self):
        run = self._run_summary(collection_failed=True)

        review = build_container_review(run, "container-host")

        self.assertEqual(review["recommendations"][0]["severity"], "critical")
        self.assertIn(
            "collect --server container-host --dry-run",
            review["recommendations"][0]["dry_run_command"],
        )

    def test_build_container_review_reports_sudo_profile_blocker(self):
        action_path = Path("tests/.tmp/container-review-action.json")
        action_path.parent.mkdir(parents=True, exist_ok=True)
        action_path.write_text(
            json.dumps({"stderr": "sudo: a password is required"}),
            encoding="utf-8",
        )

        review = build_container_review(
            self._run_summary(),
            "container-host",
            [
                self._action_summary(
                    action_id="run_admin_command",
                    record_path=action_path,
                    status="failed",
                )
            ],
        )

        self.assertEqual(
            review["recommendations"][0]["title"],
            "Repair container host sudoers profile",
        )

    def test_build_container_review_reports_package_update_sudo_blocker(self):
        action_path = Path("tests/.tmp/container-review-update-action.json")
        action_path.parent.mkdir(parents=True, exist_ok=True)
        action_path.write_text(
            json.dumps({"stderr": "command 1: sudo: a password is required"}),
            encoding="utf-8",
        )

        review = build_container_review(
            self._run_summary(),
            "container-host",
            [
                self._action_summary(
                    action_id="apply_package_updates",
                    record_path=action_path,
                    status="failed",
                )
            ],
        )

        self.assertEqual(
            review["recommendations"][0]["title"],
            "Repair container host sudoers profile",
        )

    def test_build_container_review_keeps_failed_sudoers_deploy_blocker(self):
        action_path = Path("tests/.tmp/container-review-sudoers-action.json")
        action_path.parent.mkdir(parents=True, exist_ok=True)
        action_path.write_text(
            json.dumps({"stderr": "sudo: a password is required"}),
            encoding="utf-8",
        )

        review = build_container_review(
            self._run_summary(),
            "container-host",
            [
                self._action_summary(
                    action_id="deploy_sudoers_profile",
                    record_path=action_path,
                    status="failed",
                )
            ],
        )

        self.assertEqual(
            review["recommendations"][0]["title"],
            "Repair container host sudoers profile",
        )

    def test_build_container_review_clears_sudo_blocker_after_success(self):
        failed_path = Path("tests/.tmp/container-review-sudoers-failed.json")
        success_path = Path("tests/.tmp/container-review-sudoers-success.json")
        failed_path.parent.mkdir(parents=True, exist_ok=True)
        failed_path.write_text(
            json.dumps({"stderr": "sudo: a password is required"}),
            encoding="utf-8",
        )
        success_path.write_text(json.dumps({"stderr": ""}), encoding="utf-8")

        review = build_container_review(
            self._run_summary(),
            "container-host",
            [
                self._action_summary(
                    action_id="deploy_sudoers_profile",
                    record_path=success_path,
                    status="completed",
                ),
                self._action_summary(
                    action_id="deploy_sudoers_profile",
                    record_path=failed_path,
                    status="failed",
                ),
            ],
        )

        titles = [item["title"] for item in review["recommendations"]]
        self.assertNotIn("Repair container host sudoers profile", titles)

    def test_build_container_review_reports_watchtower_api_mismatch(self):
        action_path = Path("tests/.tmp/container-review-watchtower-action.json")
        action_path.parent.mkdir(parents=True, exist_ok=True)
        action_path.write_text(
            json.dumps(
                {
                    "stdout": "watchtower Restarting (1) 7 seconds ago",
                    "stderr": (
                        "Error response from daemon: client version 1.25 is too old. "
                        "Minimum supported API version is 1.40, please upgrade your client"
                    ),
                }
            ),
            encoding="utf-8",
        )

        review = build_container_review(
            self._run_summary(),
            "container-host",
            [
                self._action_summary(
                    action_id="inspect_docker_container",
                    record_path=action_path,
                    status="completed",
                    arguments={"container": "watchtower"},
                )
            ],
        )

        titles = [item["title"] for item in review["recommendations"]]
        self.assertIn("Migrate outdated watchtower deployment", titles)
        self.assertNotIn(
            "Restart watchtower if logs show a transient failure",
            titles,
        )
        replacement = next(
            item
            for item in review["recommendations"]
            if item["title"] == "Migrate outdated watchtower deployment"
        )
        self.assertEqual(replacement["action_id"], "migrate_watchtower_container")
        self.assertIn(
            "migrate_watchtower_container",
            replacement["dry_run_command"],
        )

    def test_render_container_review_includes_recommendations(self):
        review = build_container_review(self._run_summary(), "container-host")
        html = render_container_review(review)

        self.assertIn("HomeOps Container Review", html)
        self.assertIn("Recommended Next Steps", html)
        self.assertIn("Inspect watchtower restart loop", html)
        self.assertIn("container-review.json", html)
        self.assertIn("Container Inventory", html)
        self.assertIn("monitoring-prometheus-1", html)
        self.assertIn("0.0.0.0:9090", html)
        self.assertIn("/srv/prometheus", html)

    def test_render_container_review_includes_sanitized_storage_evidence(self):
        review = build_container_review(
            self._run_summary(),
            "container-host",
            evidence={
                "observed_at": "2026-07-20T18:36:00Z",
                "method": "read-only test probe",
                "storage": {
                    "external_device_detected": False,
                    "host_disk": {"model": "Test SSD", "size_bytes": 250000000000},
                    "root_filesystem": {
                        "filesystem": "ext4",
                        "size_bytes": 100000000000,
                        "available_bytes": 80000000000,
                        "used_percent": 20,
                    },
                    "targets": [
                        {
                            "path": "/mnt/storage1",
                            "backing_target": "/",
                            "source": "/dev/mapper/root",
                            "filesystem": "ext4",
                            "aggregate_bytes": 12288,
                            "top_level_directories": 2,
                            "sentinel_present": False,
                        }
                    ],
                },
                "databases": [
                    {
                        "container": "nonprofit-postgres",
                        "engine": "PostgreSQL 15",
                        "volume": "nonprofit_postgres_data",
                        "volume_bytes": 47820800,
                        "query_status": "success",
                        "databases": [{"name": "nonprofit_app", "size_bytes": 7504387}],
                    }
                ],
            },
        )

        html = render_container_review(review)
        titles = [item["title"] for item in review["recommendations"]]

        self.assertIn("Storage and Database Evidence", html)
        self.assertIn("/mnt/storage1", html)
        self.assertIn("nonprofit_app", html)
        self.assertIn(
            "Reserve real external storage before household data deployment",
            titles,
        )

    def test_render_container_review_includes_gated_desired_workloads(self):
        review = build_container_review(
            self._run_summary(),
            "container-host",
            workloads={
                "network_scope": "lan_only",
                "workloads": [
                    {
                        "workload_id": "documents",
                        "phase": 4,
                        "state": "planned",
                        "purpose": "Household document center",
                        "services": ["paperless-ngx"],
                        "storage_class": "mixed",
                        "deployment_enabled": False,
                        "prerequisites": ["attach the 1 TB USB drive"],
                    }
                ],
            },
        )

        html = render_container_review(review)

        self.assertIn("Desired Workloads", html)
        self.assertIn("paperless-ngx", html)
        self.assertIn("attach the 1 TB USB drive", html)
        self.assertIn("gated", html)

    def test_build_container_review_uses_local_disposition_recommendations(self):
        review = build_container_review(self._run_summary(), "container-host")

        titles = [item["title"] for item in review["recommendations"]]
        self.assertIn("Move useful monitoring services into desired state", titles)
        monitoring = next(
            item
            for item in review["recommendations"]
            if item["title"] == "Move useful monitoring services into desired state"
        )
        self.assertEqual(monitoring["action_id"], "deploy_monitoring_stack")
        self.assertIn("--dry-run", monitoring["dry_run_command"])
        container = review["server"]["docker"]["containers"][0]
        self.assertEqual(container["classification"], "redeploy")
        self.assertIn("pinned image", container["classification_rationale"])

    def test_build_container_review_recommends_bounded_disposable_retirement(self):
        run = self._run_summary()
        run.servers[0]["docker"]["containers"].append(
            {
                "name": "filebrowser",
                "image": "filebrowser/filebrowser:latest",
                "state": "running",
                "health": "healthy",
                "restart_policy": "unless-stopped",
                "network_mode": "dashboards_default",
                "ports": [],
                "mounts": [],
            }
        )

        with patch(
            "controller.container_review.load_container_classifications",
            return_value={
                "filebrowser": {
                    "classification": "retire_now",
                    "rationale": "confirmed disposable",
                }
            },
        ):
            review = build_container_review(run, "container-host", evidence={})
        retirement = next(
            item
            for item in review["recommendations"]
            if item["title"] == "Retire confirmed disposable containers"
        )

        self.assertEqual(retirement["action_id"], "retire_disposable_containers")
        self.assertIn("--dry-run", retirement["dry_run_command"])

    def test_write_container_review_writes_json_and_html(self):
        output_dir = Path("tests/.tmp/container-review")
        if output_dir.exists():
            shutil.rmtree(output_dir)

        review = write_container_review(
            self._run_summary(),
            "container-host",
            output_dir=output_dir,
            generated_at="2026-05-26T18:00:00Z",
        )

        self.assertTrue(review.json_path.exists())
        self.assertTrue(review.html_path.exists())
        payload = json.loads(review.json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["review_type"], "container_review")

    def _run_summary(self, collection_failed: bool = False) -> RunSummary:
        findings = []
        servers = []
        collection_errors = []
        if collection_failed:
            findings.append(
                {
                    "severity": "critical",
                    "server_id": "container-host",
                    "code": "collection_failed",
                    "message": "Health command exited with code 255.",
                    "recommended_action_ids": [],
                }
            )
            collection_errors.append(
                {
                    "server_id": "container-host",
                    "message": "Health command exited with code 255.",
                }
            )
        else:
            findings.extend(
                [
                    {
                        "severity": "warning",
                        "server_id": "container-host",
                        "code": "docker_unhealthy_container",
                        "message": "Container watchtower is reporting Restarting.",
                        "recommended_action_ids": ["restart_docker_container"],
                    },
                    {
                        "severity": "warning",
                        "server_id": "container-host",
                        "code": "reboot_required",
                        "message": "The server reports that a reboot is required.",
                        "recommended_action_ids": ["reboot_server"],
                    },
                ]
            )
            servers.append(
                {
                    "server_id": "container-host",
                    "role": "container_host",
                    "hostname": "containerserver",
                    "collected_at": "2026-05-26T17:00:43Z",
                    "updates": {
                        "pending_total": 7,
                        "pending_security": 0,
                        "reboot_required": True,
                    },
                    "resources": {
                        "cpu_count": 4,
                        "load_1m": 0.28,
                        "memory_used_percent": 17.5,
                        "swap_used_percent": 0.0,
                    },
                    "services": [
                        {"name": "ssh", "state": "active", "enabled": False},
                        {"name": "docker", "state": "active", "enabled": True},
                    ],
                    "docker": {
                        "installed": True,
                        "containers_total": 9,
                        "containers_running": 9,
                        "inventory_collected": True,
                        "containers": [
                            {
                                "name": "monitoring-prometheus-1",
                                "image": "prom/prometheus:v3",
                                "state": "running",
                                "health": "none",
                                "restart_policy": "unless-stopped",
                                "network_mode": "monitoring_default",
                                "compose_project": "monitoring",
                                "compose_service": "prometheus",
                                "ports": [
                                    {
                                        "container_port": "9090/tcp",
                                        "host_ip": "0.0.0.0",
                                        "host_port": "9090",
                                    }
                                ],
                                "mounts": [
                                    {
                                        "type": "bind",
                                        "source": "/srv/prometheus",
                                        "destination": "/prometheus",
                                        "read_only": False,
                                    }
                                ],
                            }
                        ],
                        "unhealthy": [
                            {
                                "name": "watchtower",
                                "status": "Restarting (1) 4 seconds ago",
                            }
                        ],
                    },
                }
            )

        return RunSummary(
            run_id="2026-05-26T17-00-16Z",
            generated_at="2026-05-26T17:00:16Z",
            generated_dt=datetime.fromisoformat("2026-05-26T17:00:16+00:00"),
            fleet_path=Path("history/runs/2026-05-26T17-00-16Z/fleet-health.json"),
            servers_checked=len(servers),
            servers_failed=len(collection_errors),
            counts={"critical": len(collection_errors), "warning": 2, "info": 0},
            findings=findings,
            servers=servers,
            collection_errors=collection_errors,
        )

    def _action_summary(
        self,
        action_id: str = "reboot_server",
        record_path: Path = Path("history/actions/action.json"),
        status: str = "dry_run",
        arguments: dict | None = None,
    ) -> ActionSummary:
        return ActionSummary(
            timestamp="2026-05-12T22:42:22Z",
            timestamp_dt=datetime(2026, 5, 12, 22, 42, 22, tzinfo=timezone.utc),
            record_path=record_path,
            server_id="container-host",
            action_id=action_id,
            status=status,
            risk="approval_required",
            dry_run=True,
            arguments=arguments or {},
            approval_source="dry_run",
            command=["ssh", "container-host", "sudo", "shutdown"],
            exit_code=None,
            message="Action was validated but not executed.",
        )


if __name__ == "__main__":
    unittest.main()
