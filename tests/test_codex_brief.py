from datetime import datetime
from pathlib import Path
import shutil
import unittest

from controller.codex_brief import (
    extract_tracker_next_step,
    render_codex_brief,
    write_codex_brief,
)
from controller.history import RunSummary
from controller.main import build_parser, command_codex_brief


class CodexBriefTests(unittest.TestCase):
    def test_render_codex_brief_stays_focused_on_resume_sources(self):
        brief = render_codex_brief(
            [self._run_summary()],
            output_dir=Path("reports/generated"),
            active_work_path=Path("ACTIVE_WORK.md"),
            tracker_path=Path("tests/.tmp/missing-tracker.md"),
            generated_at="2026-05-28T12:00:00Z",
        )

        self.assertIn("Quick resume.", brief)
        self.assertIn("ACTIVE_WORK.md", brief)
        self.assertIn("reports/generated/codex-brief.md", brief)
        self.assertIn("2026-05-26T19-38-51Z", brief)
        self.assertIn("0 critical, 1 warning, 1 info", brief)
        self.assertIn("Do not re-read the whole repository.", brief)

    def test_write_codex_brief_creates_generated_markdown(self):
        output_dir = Path("tests/.tmp/codex-brief-output")
        if output_dir.exists():
            shutil.rmtree(output_dir)

        path = write_codex_brief(
            [self._run_summary()],
            output_dir=output_dir,
            active_work_path=Path("ACTIVE_WORK.md"),
            tracker_path=Path("tests/.tmp/missing-tracker.md"),
        )

        self.assertEqual(path.name, "codex-brief.md")
        self.assertTrue(path.exists())
        self.assertIn("Codex Brief", path.read_text(encoding="utf-8"))

    def test_extract_tracker_next_step_caps_section(self):
        tracker = Path("tests/.tmp/codex-brief-tracker.md")
        tracker.parent.mkdir(parents=True, exist_ok=True)
        tracker.write_text(
            "# Tracker\n\n"
            "## Next Implementation Step\n\n"
            "First line.\n"
            "Second line.\n"
            "Third line.\n\n"
            "## Later Section\n\n"
            "Ignore me.\n",
            encoding="utf-8",
        )

        section = extract_tracker_next_step(tracker, max_lines=2)

        self.assertEqual(section, ["First line.", "Second line."])

    def test_parser_wires_codex_brief_command(self):
        args = build_parser().parse_args(["codex-brief"])

        self.assertIs(args.func, command_codex_brief)

    def _run_summary(self) -> RunSummary:
        return RunSummary(
            run_id="2026-05-26T19-38-51Z",
            generated_at="2026-05-26T19:38:51Z",
            generated_dt=datetime.fromisoformat("2026-05-26T19:38:51+00:00"),
            fleet_path=Path("history/runs/2026-05-26T19-38-51Z/fleet-health.json"),
            servers_checked=3,
            servers_failed=0,
            counts={"critical": 0, "warning": 1, "info": 1},
            findings=[],
            servers=[],
            collection_errors=[],
        )


if __name__ == "__main__":
    unittest.main()
