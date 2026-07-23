"""Validate and rotate encrypted Mission Control backup artifacts."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import re
from pathlib import Path


KEY_RE = re.compile(rb"^[A-Za-z0-9_-]{64}$")
HMAC_RE = re.compile(r"^[0-9a-f]{64}$")
HMAC_CONTEXT = b"homeops-mission-control-backup-hmac-v1"


class BackupArtifactError(ValueError):
    """Raised when a protected backup artifact fails validation."""


def read_key(path: Path) -> bytes:
    """Read and validate the fixed-format backup master key."""

    if path.is_symlink() or not path.is_file():
        raise BackupArtifactError(f"Backup key is not a regular file: {path}")
    value = path.read_bytes().strip()
    if not KEY_RE.fullmatch(value):
        raise BackupArtifactError("Backup key has an invalid format")
    return value


def prepare_incoming(destination: Path) -> None:
    """Create the ignored destination and remove only stale incoming files."""

    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or not destination.is_dir():
        raise BackupArtifactError(f"Backup destination is unsafe: {destination}")
    for name in ("mission-control.incoming.enc", "mission-control.incoming.hmac"):
        path = destination / name
        if path.is_symlink():
            raise BackupArtifactError(f"Incoming backup path is a symlink: {path}")
        if path.exists():
            path.unlink()


def _ciphertext_hmac(ciphertext: Path, master_key: bytes) -> str:
    hmac_key = hmac.new(master_key, HMAC_CONTEXT, hashlib.sha256).digest()
    digest = hmac.new(hmac_key, digestmod=hashlib.sha256)
    with ciphertext.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_pair(ciphertext: Path, sidecar: Path, key_path: Path) -> int:
    """Authenticate one encrypted backup pair without changing it."""

    for path in (ciphertext, sidecar):
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise BackupArtifactError(f"Backup artifact is invalid: {path}")

    expected = sidecar.read_text(encoding="ascii").strip()
    if not HMAC_RE.fullmatch(expected):
        raise BackupArtifactError("Backup HMAC sidecar has an invalid format")
    actual = _ciphertext_hmac(ciphertext, read_key(key_path))
    if not hmac.compare_digest(actual, expected):
        raise BackupArtifactError("Backup ciphertext HMAC verification failed")
    return ciphertext.stat().st_size


def validate_current(destination: Path, key_path: Path) -> int:
    """Authenticate the fixed current backup pair for a restore action."""

    if destination.is_symlink() or not destination.is_dir():
        raise BackupArtifactError(f"Backup destination is unsafe: {destination}")
    return validate_pair(
        destination / "mission-control.current.enc",
        destination / "mission-control.current.hmac",
        key_path,
    )


def promote_incoming(destination: Path, key_path: Path) -> None:
    """Authenticate incoming files, then retain current plus one previous set."""

    prepare_names = {
        "ciphertext": destination / "mission-control.incoming.enc",
        "sidecar": destination / "mission-control.incoming.hmac",
        "current_ciphertext": destination / "mission-control.current.enc",
        "current_sidecar": destination / "mission-control.current.hmac",
        "previous_ciphertext": destination / "mission-control.previous.enc",
        "previous_sidecar": destination / "mission-control.previous.hmac",
    }
    ciphertext = prepare_names["ciphertext"]
    sidecar = prepare_names["sidecar"]
    validate_pair(ciphertext, sidecar, key_path)

    current_pair = (
        prepare_names["current_ciphertext"],
        prepare_names["current_sidecar"],
    )
    if current_pair[0].exists() != current_pair[1].exists():
        raise BackupArtifactError("Current backup pair is incomplete; refusing rotation")
    for path in prepare_names.values():
        if path.is_symlink():
            raise BackupArtifactError(f"Backup artifact path is a symlink: {path}")

    previous_pair = (
        prepare_names["previous_ciphertext"],
        prepare_names["previous_sidecar"],
    )
    for path in previous_pair:
        if path.exists():
            path.unlink()
    if current_pair[0].exists():
        current_pair[0].replace(previous_pair[0])
        current_pair[1].replace(previous_pair[1])
    ciphertext.replace(current_pair[0])
    sidecar.replace(current_pair[1])
    print(
        "mission_control_backup_authenticated "
        f"bytes={current_pair[0].stat().st_size} retention=current+previous"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-key")
    validate.add_argument("--path", type=Path, required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--destination", type=Path, required=True)

    promote = subparsers.add_parser("promote")
    promote.add_argument("--destination", type=Path, required=True)
    promote.add_argument("--key", type=Path, required=True)

    validate_current_parser = subparsers.add_parser("validate-current")
    validate_current_parser.add_argument("--destination", type=Path, required=True)
    validate_current_parser.add_argument("--key", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "validate-key":
            read_key(args.path)
            print("mission_control_backup_key_valid")
        elif args.command == "prepare":
            prepare_incoming(args.destination)
            print("mission_control_backup_destination_ready")
        elif args.command == "promote":
            promote_incoming(args.destination, args.key)
        else:
            size = validate_current(args.destination, args.key)
            print(f"mission_control_current_backup_authenticated bytes={size}")
    except (BackupArtifactError, OSError, UnicodeError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
