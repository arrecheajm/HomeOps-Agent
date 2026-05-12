from datetime import datetime
from pathlib import Path
import json
import shutil
import unittest

from controller.before_state import (
    BeforeStateError,
    build_before_state_snapshot,
    write_before_state_snapshot,
)
from controller.history import ActionSummary, RunSummary
from controller.inventory import ServerInventoryItem


class BeforeStateTests(unittest.TestCase):
    def setUp(self):
        self.output_dir = Path("tests/.tmp/before-state")
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True)

    def test_write_snapshot_for_rebuildable_server(self):
        snapshot = write_before_state_snapshot(
            self._run_summary(),
            self._ispy_server(),
            "before AgentDVR overhaul",
            [self._action_summary()],
            output_dir=self.output_dir,
            generated_at="2026-05-12T21:00:00Z",
        )

        self.assertTrue(snapshot.path.exists())
        self.assertEqual(
            snapshot.path.name,
            "2026-05-12T21-00-00Z-ispy-server.json",
        )
        payload = json.loads(snapshot.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["snapshot_type"], "before_rebuild")
        self.assertEqual(payload["server_id"], "ispy-server")
        self.assertEqual(payload["access_profile"], "experimental")
        self.assertTrue(payload["rebuildable"])
        self.assertEqual(payload["source"]["run_id"], "2026-05-12T20-00-00Z")
        self.assertEqual(payload["server"]["hostname"], "spybox")
        self.assertEqual(payload["findings"][0]["code"], "service_failed")
        self.assertEqual(payload["recent_actions"][0]["action_id"], "restart_service")
        self.assertTrue(
            payload["rebuild_readiness"]["eligible_for_rebuild_planning"]
        )

    def test_rejects_non_rebuildable_server(self):
        with self.assertRaisesRegex(BeforeStateError, "not marked rebuildable"):
            build_before_state_snapshot(
                self._run_summary(),
                self._openvpn_server(),
                "before guarded rebuild",
                generated_at="2026-05-12T21:00:00Z",
            )

    def test_missing_server_in_source_run_is_rejected(self):
        with self.assertRaisesRegex(BeforeStateError, "not present"):
            build_before_state_snapshot(
                self._run_summary(),
                ServerInventoryItem(
                    server_id="container-host",
                    role="container_host",
                    host="container-host.local",
                    user="homeops",
                    access_profile="lab",
                    rebuildable=True,
                ),
                "before container rebuild",
                generated_at="2026-05-12T21:00:00Z",
            )

    def test_collection_errors_block_rebuild_readiness(self):
        payload = build_before_state_snapshot(
            self._run_summary(collection_errors=True),
            self._ispy_server(),
            "before AgentDVR overhaul",
            generated_at="2026-05-12T21:00:00Z",
        )

        readiness = payload["rebuild_readiness"]
        self.assertFalse(readiness["eligible_for_rebuild_planning"])
        self.assertIn("collection errors", readiness["blocked_reasons"][0])

    def _run_summary(self, collection_errors: bool = False) -> RunSummary:
        errors = []
        if collection_errors:
            errors.append(
                {
                    "server_id": "ispy-server",
                    "message": "Health command exited with code 1.",
                }
            )

        return RunSummary(
            run_id="2026-05-12T20-00-00Z",
            generated_at="2026-05-12T20:00:00Z",
            generated_dt=datetime.fromisoformat("2026-05-12T20:00:00+00:00"),
            fleet_path=Path("history/runs/2026-05-12T20-00-00Z/fleet-health.json"),
            servers_checked=1,
            servers_failed=len(errors),
            counts={"critical": 0, "warning": 1, "info": 0},
            findings=[
                {
                    "severity": "warning",
                    "server_id": "ispy-server",
                    "code": "service_failed",
                    "message": "Legacy ispy service is failed.",
                }
            ],
            servers=[
                {
                    "server_id": "ispy-server",
                    "role": "ispy_server",
                    "hostname": "spybox",
                    "collected_at": "2026-05-12T19:59:00Z",
                    "os": {"name": "Ubuntu", "version": "24.04"},
                    "services": [
                        {"name": "AgentDVR", "state": "active", "enabled": True}
                    ],
                    "updates": {"pending_total": 71, "reboot_required": True},
                }
            ],
            collection_errors=errors,
        )

    def _action_summary(self) -> ActionSummary:
        return ActionSummary(
            timestamp="2026-05-12T19:30:00Z",
            timestamp_dt=datetime.fromisoformat("2026-05-12T19:30:00+00:00"),
            record_path=Path("history/actions/action.json"),
            server_id="ispy-server",
            action_id="restart_service",
            status="dry_run",
            risk="approval_required",
            dry_run=True,
            arguments={"service": "AgentDVR.service"},
            approval_source="dry_run",
            command=["ssh", "ispy-server", "sudo systemctl restart AgentDVR"],
            exit_code=None,
            message="Action was validated but not executed.",
        )

    def _ispy_server(self) -> ServerInventoryItem:
        return ServerInventoryItem(
            server_id="ispy-server",
            role="ispy_server",
            host="ispy-server.local",
            user="homeops",
            access_profile="experimental",
            rebuildable=True,
        )

    def _openvpn_server(self) -> ServerInventoryItem:
        return ServerInventoryItem(
            server_id="openvpn-server",
            role="openvpn_server",
            host="openvpn-server.local",
            user="homeops",
            access_profile="guarded",
            rebuildable=False,
        )


if __name__ == "__main__":
    unittest.main()
