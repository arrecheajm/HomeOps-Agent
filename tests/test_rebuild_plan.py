from pathlib import Path
import json
import shutil
import unittest

from controller.rebuild_plan import (
    RebuildPlanError,
    build_rebuild_plan,
    find_latest_before_state,
    load_before_state,
    write_rebuild_plan,
)
from controller.inventory import ServerInventoryItem


class RebuildPlanTests(unittest.TestCase):
    def setUp(self):
        self.output_dir = Path("tests/.tmp/rebuild-plans")
        self.before_state_dir = Path("tests/.tmp/rebuild-before-state")
        for path in (self.output_dir, self.before_state_dir):
            if path.exists():
                shutil.rmtree(path)
            path.mkdir(parents=True)

    def test_write_rebuild_plan_from_before_state(self):
        before_path = self._write_before_state(
            "2026-05-12T20-00-00Z-ispy-server.json",
            self._before_state_payload(),
        )

        plan = write_rebuild_plan(
            self._ispy_server(),
            load_before_state(before_path),
            before_path,
            "rebuild AgentDVR cleanly",
            "reinstall",
            output_dir=self.output_dir,
            generated_at="2026-05-12T21:30:00Z",
        )

        self.assertTrue(plan.path.exists())
        self.assertEqual(
            plan.path.name,
            "2026-05-12T21-30-00Z-ispy-server-rebuild-plan.json",
        )
        payload = json.loads(plan.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["plan_type"], "rebuild_plan")
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["server_id"], "ispy-server")
        self.assertEqual(payload["strategy"], "reinstall")
        self.assertFalse(payload["execution_allowed"])
        self.assertIn("AgentDVR configuration", self._preserve_names(payload))
        self.assertIn(
            "Verify AgentDVR service is active",
            " ".join(payload["verification"]),
        )
        self.assertEqual(
            payload["future_destructive_approval"],
            "Approve destructive rebuild plan "
            "2026-05-12T21-30-00Z-ispy-server-rebuild-plan on ispy-server",
        )

    def test_rejects_non_rebuildable_server(self):
        with self.assertRaisesRegex(RebuildPlanError, "not marked rebuildable"):
            build_rebuild_plan(
                self._openvpn_server(),
                self._before_state_payload(server_id="openvpn-server"),
                Path("history/before-state/openvpn.json"),
                "rebuild VPN",
                "repair",
                generated_at="2026-05-12T21:30:00Z",
            )

    def test_rejects_mismatched_before_state(self):
        with self.assertRaisesRegex(RebuildPlanError, "does not match"):
            build_rebuild_plan(
                self._ispy_server(),
                self._before_state_payload(server_id="container-host"),
                Path("history/before-state/container.json"),
                "rebuild AgentDVR",
                "repair",
                generated_at="2026-05-12T21:30:00Z",
            )

    def test_before_state_collection_errors_make_blocked_plan(self):
        payload = build_rebuild_plan(
            self._ispy_server(),
            self._before_state_payload(blocked=True),
            Path("history/before-state/ispy.json"),
            "rebuild AgentDVR",
            "repair",
            generated_at="2026-05-12T21:30:00Z",
        )

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(
            payload["blocked_reasons"],
            ["Latest source run has collection errors for this server."],
        )

    def test_find_latest_before_state_by_server(self):
        older = self._write_before_state(
            "2026-05-12T20-00-00Z-ispy-server.json",
            self._before_state_payload(generated_at="2026-05-12T20:00:00Z"),
        )
        latest = self._write_before_state(
            "2026-05-12T21-00-00Z-ispy-server.json",
            self._before_state_payload(generated_at="2026-05-12T21:00:00Z"),
        )

        self.assertEqual(
            find_latest_before_state("ispy-server", self.before_state_dir),
            latest,
        )
        self.assertNotEqual(older, latest)

    def _write_before_state(self, name: str, payload: dict) -> Path:
        path = self.before_state_dir / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _before_state_payload(
        self,
        server_id: str = "ispy-server",
        generated_at: str = "2026-05-12T20:00:00Z",
        blocked: bool = False,
    ) -> dict:
        blocked_reasons = []
        if blocked:
            blocked_reasons.append(
                "Latest source run has collection errors for this server."
            )
        return {
            "schema_version": "1.0",
            "snapshot_type": "before_rebuild",
            "generated_at": generated_at,
            "server_id": server_id,
            "access_profile": "experimental",
            "rebuildable": True,
            "intent": "before AgentDVR overhaul",
            "source": {
                "run_id": "2026-05-12T19-00-00Z",
                "fleet_path": "history/runs/2026-05-12T19-00-00Z/fleet-health.json",
            },
            "server": {
                "server_id": server_id,
                "role": "ispy_server",
                "services": [{"name": "AgentDVR", "state": "active"}],
            },
            "findings": [],
            "collection_errors": [],
            "recent_actions": [],
            "rebuild_readiness": {
                "eligible_for_rebuild_planning": not blocked,
                "blocked_reasons": blocked_reasons,
            },
        }

    def _preserve_names(self, payload: dict) -> list[str]:
        return [str(item["name"]) for item in payload["preserve"]]

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
