"""Approval phrase helpers for HomeOps actions."""

from __future__ import annotations

from typing import Any


def approval_phrase(action_id: str, server_id: str, arguments: dict[str, Any]) -> str:
    """Return the exact approval phrase required for an action request."""

    detail = _argument_detail(arguments)
    if detail:
        return f"Approve action {action_id} on {server_id} with {detail}"
    return f"Approve action {action_id} on {server_id}"


def approval_matches(
    approval_text: str | None,
    action_id: str,
    server_id: str,
    arguments: dict[str, Any],
) -> bool:
    """Return whether approval text exactly identifies the action request."""

    if not approval_text:
        return False
    return _normalize(approval_text) == _normalize(
        approval_phrase(action_id, server_id, arguments)
    )


def _argument_detail(arguments: dict[str, Any]) -> str:
    parts = []
    for key in sorted(arguments):
        value = arguments[key]
        if value is None:
            continue
        parts.append(f"{key} {value}")
    return ", ".join(parts)


def _normalize(value: str) -> str:
    return " ".join(value.strip().split())
