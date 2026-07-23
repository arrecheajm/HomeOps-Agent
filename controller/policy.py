"""Policy loading for local rule evaluation and safety checks."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import config


DEFAULT_POLICY: dict[str, Any] = {
    "auto_run_low_risk_actions": False,
    "approval_required_actions": [
        "inspect_docker_container",
        "restart_service",
        "restart_docker_container",
        "replace_watchtower_container",
        "migrate_watchtower_container",
        "retire_disposable_containers",
        "preflight_monitoring_images",
        "preflight_mission_control_images",
        "provision_mission_control_secrets",
        "provision_mission_control_backup_secret",
        "backup_mission_control_stack",
        "restore_mission_control_stack",
        "deploy_mission_control_stack",
        "rollback_mission_control_stack",
        "provision_monitoring_secret",
        "deploy_monitoring_stack",
        "repair_monitoring_grafana",
        "rollback_monitoring_stack",
        "retire_legacy_monitoring_stack",
        "retire_legacy_monitoring_files",
        "deploy_health_script",
        "deploy_sudoers_profile",
        "apply_security_updates",
        "apply_package_updates",
        "reboot_server",
        "run_admin_command",
    ],
    "forbidden_action_patterns": [
        "rm -rf",
        "ufw",
        "iptables",
        "nft",
        "firewall-cmd",
        "sshd_config",
        "/etc/openvpn",
        "openvpn --config",
        "dockerd",
        "mkfs",
        "wipefs",
        "dd if=",
        "parted",
        "sfdisk",
        "sgdisk",
        "fdisk",
    ],
    "thresholds": {
        "disk_warning_percent": 80,
        "disk_critical_percent": 95,
        "failed_ssh_login_warning_24h": 20,
        "failed_ssh_login_critical_24h": 100,
    },
}


def load_policy(path: Path | None = None) -> dict[str, Any]:
    """Load policy settings, falling back to conservative defaults."""

    policy_path = path or config.POLICY_PATH
    if not policy_path.exists():
        return deepcopy(DEFAULT_POLICY)

    text = policy_path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        raw = _load_with_yaml_if_available(text, policy_path)

    if not isinstance(raw, dict):
        raise ValueError(f"Policy root must be an object: {policy_path}")

    merged = deepcopy(DEFAULT_POLICY)
    _deep_update(merged, raw)
    return merged


def threshold(policy_data: dict[str, Any], name: str) -> int:
    """Return a named integer threshold from policy defaults plus overrides."""

    defaults = DEFAULT_POLICY["thresholds"]
    thresholds = policy_data.get("thresholds")
    if not isinstance(thresholds, dict):
        thresholds = {}

    value = thresholds.get(name, defaults[name])
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(defaults[name])


def _load_with_yaml_if_available(text: str, path: Path) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ValueError(
            f"{path} is not JSON-compatible YAML and PyYAML is not installed."
        ) from exc

    return yaml.safe_load(text)


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
