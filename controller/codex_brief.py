"""Compact Codex session brief generation."""

from __future__ import annotations

from pathlib import Path

from . import config
from .history import RunSummary


DEFAULT_BRIEF_FILENAME = "codex-brief.md"
TRACKER_NEXT_STEP_HEADING = "## Next Implementation Step"


def render_codex_brief(
    runs: list[RunSummary],
    *,
    output_dir: Path | None = None,
    active_work_path: Path | None = None,
    tracker_path: Path | None = None,
    generated_at: str | None = None,
) -> str:
    """Render a deliberately compact startup brief for Codex sessions."""

    actual_output_dir = output_dir or config.GENERATED_REPORTS_DIR
    actual_active_work_path = active_work_path or config.ACTIVE_WORK_PATH
    actual_tracker_path = tracker_path or (config.BASE_DIR / "IMPLEMENTATION_TRACKER.md")
    latest = runs[0] if runs else None
    generated = generated_at or config.utc_now_iso()

    lines = [
        "# Codex Brief",
        "",
        f"Generated: {generated}",
        "",
        "Purpose: provide a small session-start context file. Use this with "
        "`ACTIVE_WORK.md` instead of running a full project review.",
        "",
        "## Read First",
        "",
        f"- Daily handoff: `{_display_path(actual_active_work_path)}`",
        f"- This brief: `{_display_path(actual_output_dir / DEFAULT_BRIEF_FILENAME)}`",
        "- Full fleet review is intentionally separate and more expensive.",
        "",
        "## Report Pointers",
        "",
        f"- Dashboard: `{_display_path(actual_output_dir / 'index.html')}`",
        f"- Fleet catalog HTML: `{_display_path(actual_output_dir / 'fleet-catalog.html')}`",
        f"- Fleet catalog JSON: `{_display_path(config.FLEET_CATALOG_PATH)}`",
    ]

    if latest:
        lines.extend(
            [
                f"- Latest run: `{latest.run_id}`",
                f"- Latest fleet JSON: `{_display_path(latest.fleet_path)}`",
                "",
                "## Latest Run Snapshot",
                "",
                f"- Generated at: `{latest.generated_at}`",
                f"- Servers checked: {latest.servers_checked}",
                f"- Servers failed: {latest.servers_failed}",
                "- Findings: "
                f"{latest.counts.get('critical', 0)} critical, "
                f"{latest.counts.get('warning', 0)} warning, "
                f"{latest.counts.get('info', 0)} info",
            ]
        )
        if latest.collection_errors:
            error_ids = ", ".join(
                str(error.get("server_id") or "unknown")
                for error in latest.collection_errors[:5]
            )
            lines.append(f"- Collection errors: {error_ids}")
        else:
            lines.append("- Collection errors: none")
    else:
        lines.extend(
            [
                "- Latest run: none found",
                "",
                "## Latest Run Snapshot",
                "",
                "- No run history found. Run collection before fleet-specific work.",
            ]
        )

    next_step = extract_tracker_next_step(actual_tracker_path)
    if next_step:
        lines.extend(["", "## Tracker Next Step", "", *next_step])

    lines.extend(
        [
            "",
            "## Quick Resume Prompt",
            "",
            "```text",
            "Quick resume. Read ACTIVE_WORK.md and reports/generated/codex-brief.md "
            "only, then continue the next step. Use the thinking level guidance in "
            "ACTIVE_WORK.md. Keep output concise.",
            "```",
            "",
            "## Avoid By Default",
            "",
            "- Do not re-read the whole repository.",
            "- Do not run `run fleet review` unless live fleet status is needed.",
            "- Do not inspect archived docs unless the current docs are missing context.",
            "",
        ]
    )
    return "\n".join(lines)


def write_codex_brief(
    runs: list[RunSummary],
    *,
    output_dir: Path | None = None,
    active_work_path: Path | None = None,
    tracker_path: Path | None = None,
) -> Path:
    """Write the compact Codex brief and return its path."""

    actual_output_dir = output_dir or config.GENERATED_REPORTS_DIR
    actual_output_dir.mkdir(parents=True, exist_ok=True)
    path = actual_output_dir / DEFAULT_BRIEF_FILENAME
    path.write_text(
        render_codex_brief(
            runs,
            output_dir=actual_output_dir,
            active_work_path=active_work_path,
            tracker_path=tracker_path,
        ),
        encoding="utf-8",
    )
    return path


def extract_tracker_next_step(path: Path, max_lines: int = 8) -> list[str]:
    """Extract the first concise next-step paragraph from the tracker."""

    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == TRACKER_NEXT_STEP_HEADING:
            start = index + 1
            break
    if start is None:
        return []

    section: list[str] = []
    in_paragraph = False
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if not line.strip():
            if in_paragraph:
                break
            continue
        in_paragraph = True
        section.append(line)
        if len([item for item in section if item.strip()]) >= max_lines:
            break
    return section


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(config.BASE_DIR).as_posix()
    except ValueError:
        return path.as_posix()
