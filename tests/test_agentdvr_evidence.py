from pathlib import Path
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch

from controller.agentdvr_evidence import (
    AgentDvrEvidenceError,
    build_agentdvr_evidence_command,
    collect_agentdvr_evidence,
)
from controller.inventory import ServerInventoryItem
from controller.main import build_parser, command_agentdvr_evidence


class AgentDvrEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.output_dir = Path("tests/.tmp/agentdvr-evidence")
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True)

    def test_build_agentdvr_evidence_command_uses_fixed_sudo_python_script(self):
        command = build_agentdvr_evidence_command(self._ispy_server())

        self.assertEqual(command[0], "ssh")
        self.assertIn("spy@ispy-server.local", command)
        self.assertEqual(
            command[-1],
            "sudo -n /usr/bin/bash -lc 'python3 -'",
        )

    def test_collect_agentdvr_evidence_writes_sanitized_json(self):
        output_path = self.output_dir / "evidence.json"
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout=json.dumps(self._payload()),
            stderr="",
        )

        with patch("controller.agentdvr_evidence.subprocess.run", return_value=completed) as run:
            result = collect_agentdvr_evidence(
                self._ispy_server(),
                output_path=output_path,
            )

        self.assertEqual(result.output_path, output_path)
        self.assertTrue(output_path.exists())
        self.assertEqual(result.payload["camera_count"], 1)
        written = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(written["endpoint_checks"][0]["host_last_octet"], "166")
        self.assertNotIn("rtsp://", json.dumps(written))
        self.assertNotIn("source_uri", written["cameras"][0])
        self.assertIn("Collect sanitized AgentDVR camera evidence", run.call_args.kwargs["input"])

    def test_collect_agentdvr_evidence_rejects_stream_uri_output(self):
        payload = self._payload()
        payload["cameras"][0]["source_uri"] = "rtsp://user:pass@example/live"
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        with patch("controller.agentdvr_evidence.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(AgentDvrEvidenceError, "must not include stream URIs"):
                collect_agentdvr_evidence(
                    self._ispy_server(),
                    output_path=self.output_dir / "evidence.json",
                )

    def test_parser_wires_agentdvr_evidence_command(self):
        args = build_parser().parse_args(["agentdvr-evidence"])

        self.assertIs(args.func, command_agentdvr_evidence)

    def _payload(self) -> dict:
        return {
            "generated_at": "2026-05-29T12:00:00Z",
            "camera_count": 1,
            "microphone_count": 0,
            "media_total_mb": 1.0,
            "endpoint_checks": [
                {
                    "camera": "Camera 4",
                    "host_last_octet": "166",
                    "protocol": "rtsp",
                    "port": 554,
                    "path_label": "/live",
                    "tcp_reachable": False,
                    "tcp_error": "ConnectionRefusedError",
                    "rtsp_options_status": "",
                }
            ],
            "cameras": [
                {
                    "id": "4",
                    "name": "Camera 4",
                    "source_uri_present": True,
                    "recording_file_count": 0,
                }
            ],
        }

    def _ispy_server(self) -> ServerInventoryItem:
        return ServerInventoryItem(
            server_id="ispy-server",
            role="ispy_server",
            host="ispy-server.local",
            user="spy",
            identity_file="~/.ssh/homeops_ed25519",
            access_profile="experimental",
            rebuildable=True,
        )


if __name__ == "__main__":
    unittest.main()
