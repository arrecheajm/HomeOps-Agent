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
        "restart_service",
        "restart_docker_container",
        "deploy_health_script",
        "apply_security_updates",
        "reboot_server",
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
