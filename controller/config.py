"""Shared controller paths and timestamp helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
ACTIVE_WORK_PATH = BASE_DIR / "ACTIVE_WORK.md"
CONFIG_DIR = BASE_DIR / "config"
REPORTS_DIR = BASE_DIR / "reports"
GENERATED_REPORTS_DIR = REPORTS_DIR / "generated"
HISTORY_DIR = BASE_DIR / "history"
RUNS_DIR = HISTORY_DIR / "runs"
ACTIONS_DIR = HISTORY_DIR / "actions"
BEFORE_STATE_DIR = HISTORY_DIR / "before-state"
REBUILD_PLANS_DIR = HISTORY_DIR / "rebuild-plans"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
FLEET_CATALOG_PATH = KNOWLEDGE_DIR / "fleet-catalog.json"
CONTAINER_CLASSIFICATIONS_PATH = CONFIG_DIR / "container-classifications.yaml"
CONTAINER_REVIEW_EVIDENCE_PATH = CONFIG_DIR / "container-review-evidence.yaml"
WORKLOADS_PATH = CONFIG_DIR / "workloads.yaml"
DEFAULT_FIXTURE_PATH = BASE_DIR / "tests" / "fixtures" / "fleet-health.json"
DEFAULT_INVENTORY_PATH = CONFIG_DIR / "servers.yaml"
EXAMPLE_INVENTORY_PATH = CONFIG_DIR / "servers.example.yaml"
POLICY_PATH = CONFIG_DIR / "policy.yaml"


def utc_now_iso() -> str:
    """Return a compact UTC timestamp suitable for JSON."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def safe_timestamp(value: str | None = None) -> str:
    """Return a timestamp safe for filenames."""

    source = value or utc_now_iso()
    return (
        source.replace(":", "-")
        .replace("+", "-")
        .replace("/", "-")
        .replace(" ", "T")
    )
