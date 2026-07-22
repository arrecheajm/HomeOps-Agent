from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from controller.main import command_actions_run


class MainActionCommandTests(unittest.TestCase):
    def test_read_only_action_does_not_prompt_for_approval(self):
        args = Namespace(
            action_id="inspect_storage_devices",
            server="container-host",
            inventory=None,
            container=None,
            service=None,
            admin_command=None,
            intent=None,
            approval=None,
            dry_run=False,
        )
        attempt = SimpleNamespace(
            record={
                "status": "completed",
                "action_id": "inspect_storage_devices",
                "server_id": "container-host",
                "commands": [["ssh", "host", "lsblk"]],
                "command": ["ssh", "host", "lsblk"],
                "exit_code": 0,
            },
            record_path=Path("history/actions/storage.json"),
        )

        with (
            patch("controller.main.inventory.load_inventory", return_value=[]),
            patch("controller.main.sys.stdin.isatty", return_value=True),
            patch(
                "builtins.input",
                side_effect=AssertionError("read-only action prompted for approval"),
            ),
            patch("controller.main.action_runner.run_action", return_value=attempt) as run,
            patch(
                "controller.main.refresh_html_reports",
                return_value={
                    "dashboard_path": Path("reports/generated/index.html"),
                    "catalog_path": None,
                    "knowledge_path": None,
                },
            ),
            patch("controller.main.print_report_refresh"),
        ):
            result = command_actions_run(args)

        self.assertEqual(result, 0)
        self.assertIsNone(run.call_args.kwargs["approval_text"])


if __name__ == "__main__":
    unittest.main()
