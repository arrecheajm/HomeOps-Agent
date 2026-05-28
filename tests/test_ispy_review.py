from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import unittest

from controller.history import ActionSummary, RunSummary
from controller.ispy_review import (
    build_ispy_review,
    render_ispy_review,
    write_ispy_review,
)
from controller.main import build_parser, command_ispy_review


class IspyReviewTests(unittest.TestCase):
    def test_build_ispy_review_tracks_current_reliability_work(self):
        review = build_ispy_review(
            self._run_summary(),
            "ispy-server",
            [self._action_summary()],
            before_state=self._before_state(),
            before_state_path=Path(
                "history/before-state/2026-05-28T15-04-03Z-ispy-server.json"
            ),
            agentdvr_evidence=self._agentdvr_evidence(),
            agentdvr_evidence_path=Path(
                "reports/generated/ispy-agentdvr-evidence.json"
            ),
            generated_at="2026-05-28T15:30:00Z",
        )

        titles = [item["title"] for item in review["recommendations"]]
        self.assertIn("Apply security updates during a camera-safe window", titles)
        self.assertIn("Clean up failed legacy ispy.service", titles)
        self.assertIn("Fix Camera 4 stream connection refusal", titles)
        self.assertEqual(review["before_state"]["available"], True)
        self.assertEqual(review["agentdvr_evidence"]["available"], True)
        self.assertEqual(review["agentdvr_evidence"]["camera_count"], 2)
        self.assertEqual(len(review["agentdvr_evidence"]["endpoint_checks"]), 2)
        connection_check = next(
            item
            for item in review["reliability_checks"]
            if item["name"] == "Camera connection evidence"
        )
        self.assertEqual(connection_check["status"], "warning")
        self.assertEqual(
            review["before_state"]["path"],
            "history/before-state/2026-05-28T15-04-03Z-ispy-server.json",
        )
        approval = next(
            item
            for item in review["recommendations"]
            if item["title"] == "Apply security updates during a camera-safe window"
        )
        self.assertEqual(
            approval["approval_phrase"],
            "Approve action apply_security_updates on ispy-server",
        )

    def test_build_ispy_review_recommends_before_state_when_missing(self):
        review = build_ispy_review(self._run_summary(), "ispy-server")

        titles = [item["title"] for item in review["recommendations"]]

        self.assertIn("Capture before-state before cleanup", titles)
        self.assertEqual(review["before_state"]["available"], False)

    def test_render_ispy_review_includes_sections(self):
        review = build_ispy_review(
            self._run_summary(),
            "ispy-server",
            [self._action_summary()],
            before_state=self._before_state(),
            agentdvr_evidence=self._agentdvr_evidence(),
        )

        html = render_ispy_review(review)

        self.assertIn("HomeOps iSpy Review", html)
        self.assertIn("AgentDVR Evidence", html)
        self.assertIn("Service Diagnosis", html)
        self.assertIn("Camera Reliability Checklist", html)
        self.assertIn("Clean up failed legacy ispy.service", html)
        self.assertIn("host .166:554/live", html)
        self.assertIn("ispy-review.json", html)

    def test_write_ispy_review_writes_json_and_html(self):
        output_dir = Path("tests/.tmp/ispy-review")
        if output_dir.exists():
            shutil.rmtree(output_dir)

        review = write_ispy_review(
            self._run_summary(),
            "ispy-server",
            output_dir=output_dir,
            generated_at="2026-05-28T15:30:00Z",
        )

        self.assertTrue(review.json_path.exists())
        self.assertTrue(review.html_path.exists())
        payload = json.loads(review.json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["review_type"], "ispy_review")

    def test_parser_wires_ispy_review_command(self):
        args = build_parser().parse_args(["ispy-review"])

        self.assertIs(args.func, command_ispy_review)

    def _run_summary(self) -> RunSummary:
        findings = [
            {
                "severity": "warning",
                "server_id": "ispy-server",
                "code": "security_updates_pending",
                "message": "22 security updates are pending.",
                "recommended_action_ids": ["apply_security_updates"],
            },
            {
                "severity": "warning",
                "server_id": "ispy-server",
                "code": "service_failed",
                "message": "Service ispy is failed.",
                "recommended_action_ids": ["restart_service"],
            },
        ]
        return RunSummary(
            run_id="2026-05-28T15-03-53Z",
            generated_at="2026-05-28T15:03:53Z",
            generated_dt=datetime.fromisoformat("2026-05-28T15:03:53+00:00"),
            fleet_path=Path("history/runs/2026-05-28T15-03-53Z/fleet-health.json"),
            servers_checked=1,
            servers_failed=0,
            counts={"critical": 0, "warning": 2, "info": 0},
            findings=findings,
            servers=[
                {
                    "server_id": "ispy-server",
                    "role": "ispy_server",
                    "hostname": "ispyserver",
                    "collected_at": "2026-05-28T15:04:00Z",
                    "updates": {
                        "pending_total": 93,
                        "pending_security": 22,
                        "reboot_required": False,
                    },
                    "resources": {
                        "cpu_count": 4,
                        "load_1m": 0.44,
                        "memory_used_percent": 9.7,
                        "swap_used_percent": 0.0,
                    },
                    "disk": [
                        {
                            "mount": "/",
                            "size_gb": 98,
                            "free_gb": 83,
                            "used_percent": 12,
                        }
                    ],
                    "services": [
                        {"name": "ssh", "state": "active", "enabled": False},
                        {"name": "AgentDVR", "state": "active", "enabled": True},
                        {"name": "ispy", "state": "failed", "enabled": True},
                    ],
                }
            ],
            collection_errors=[],
        )

    def _before_state(self) -> dict:
        return {
            "snapshot_type": "before_rebuild",
            "generated_at": "2026-05-28T15:04:03Z",
            "intent": "before AgentDVR reliability work",
            "server_id": "ispy-server",
            "rebuild_readiness": {"eligible_for_rebuild_planning": True},
        }

    def _agentdvr_evidence(self) -> dict:
        return {
            "generated_at": "2026-05-28T17:25:42Z",
            "camera_count": 2,
            "microphone_count": 2,
            "media_total_mb": 49.0,
            "endpoint_checks": [
                {
                    "camera": "Camera 4",
                    "host_last_octet": "166",
                    "protocol": "rtsp",
                    "port": 554,
                    "path_label": "/live",
                    "tcp_reachable": False,
                    "tcp_error": "ConnectionRefusedError: [Errno 111] Connection refused",
                    "rtsp_options_status": "",
                },
                {
                    "camera": "Camera 5",
                    "host_last_octet": "164",
                    "protocol": "rtsp",
                    "port": 554,
                    "path_label": "/11",
                    "tcp_reachable": True,
                    "tcp_error": "",
                    "rtsp_options_status": "RTSP/1.0 200 OK",
                },
            ],
            "cameras": [
                {
                    "id": "4",
                    "name": "Camera 4",
                    "directory": "KDWDF",
                    "directory_present": False,
                    "resolution": "320x240",
                    "record_on_detect": "false",
                    "record_on_alert": "false",
                    "alerts_active": "true",
                    "source_uri_present": True,
                    "recording_file_count": 0,
                    "newest_recording_utc": "",
                    "recording_total_mb": 0,
                    "recent_error_count": 90,
                    "recent_exception_count": 45,
                    "recording_event_count": 0,
                    "recent_log_diagnosis": (
                        "Recent AgentDVR logs show repeated FFmpeg OPEN_INPUT "
                        "connection refused errors and reconnect attempts for Camera 4."
                    ),
                },
                {
                    "id": "5",
                    "name": "Camera 5",
                    "directory": "BENRC",
                    "directory_present": False,
                    "resolution": "320x240",
                    "record_on_detect": "false",
                    "record_on_alert": "false",
                    "alerts_active": "true",
                    "source_uri_present": True,
                    "recording_file_count": 50,
                    "newest_recording_utc": "2026-05-28T17:25:42Z",
                    "recording_total_mb": 35.64,
                    "recent_error_count": 2,
                    "recent_exception_count": 0,
                    "recording_event_count": 68,
                    "recent_log_diagnosis": (
                        "Recent AgentDVR logs show Camera 5 opening and closing recordings."
                    ),
                },
            ],
            "recording_database": {
                "file_records": 50,
                "alert_records": 100,
            },
        }

    def _action_summary(self) -> ActionSummary:
        path = Path("tests/.tmp/ispy-review-action.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "expected_approval": (
                        "Approve action apply_security_updates on ispy-server"
                    )
                }
            ),
            encoding="utf-8",
        )
        return ActionSummary(
            timestamp="2026-05-28T15:04:09Z",
            timestamp_dt=datetime(2026, 5, 28, 15, 4, 9, tzinfo=timezone.utc),
            record_path=path,
            server_id="ispy-server",
            action_id="apply_security_updates",
            status="dry_run",
            risk="approval_required",
            dry_run=True,
            arguments={},
            approval_source="dry_run",
            command=["ssh", "ispy-server", "sudo", "unattended-upgrade"],
            exit_code=None,
            message="Action was validated but not executed.",
        )


if __name__ == "__main__":
    unittest.main()
