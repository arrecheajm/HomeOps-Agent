from pathlib import Path
import hashlib
import hmac
import tempfile
import unittest

from controller.backup_artifact import (
    BackupArtifactError,
    HMAC_CONTEXT,
    prepare_incoming,
    promote_incoming,
    read_key,
)


class BackupArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.key = self.root / "backup_key"
        self.key.write_text("A" * 64 + "\n", encoding="ascii")

    def tearDown(self):
        self.temp.cleanup()

    def _write_incoming(self, payload: bytes = b"encrypted-backup") -> None:
        ciphertext = self.root / "mission-control.incoming.enc"
        ciphertext.write_bytes(payload)
        master = read_key(self.key)
        hmac_key = hmac.new(master, HMAC_CONTEXT, hashlib.sha256).digest()
        digest = hmac.new(hmac_key, payload, hashlib.sha256).hexdigest()
        (self.root / "mission-control.incoming.hmac").write_text(
            digest + "\n", encoding="ascii"
        )

    def test_prepare_removes_only_stale_incoming_files(self):
        current = self.root / "mission-control.current.enc"
        current.write_bytes(b"keep")
        self._write_incoming()

        prepare_incoming(self.root)

        self.assertTrue(current.exists())
        self.assertFalse((self.root / "mission-control.incoming.enc").exists())
        self.assertFalse((self.root / "mission-control.incoming.hmac").exists())

    def test_promote_authenticates_and_rotates_current_to_previous(self):
        (self.root / "mission-control.current.enc").write_bytes(b"old")
        (self.root / "mission-control.current.hmac").write_text(
            "0" * 64 + "\n", encoding="ascii"
        )
        self._write_incoming(b"new")

        promote_incoming(self.root, self.key)

        self.assertEqual(
            (self.root / "mission-control.current.enc").read_bytes(), b"new"
        )
        self.assertEqual(
            (self.root / "mission-control.previous.enc").read_bytes(), b"old"
        )
        self.assertFalse((self.root / "mission-control.incoming.enc").exists())

    def test_promote_rejects_tampered_ciphertext_without_rotating(self):
        current = self.root / "mission-control.current.enc"
        current.write_bytes(b"old")
        (self.root / "mission-control.current.hmac").write_text(
            "0" * 64 + "\n", encoding="ascii"
        )
        self._write_incoming()
        (self.root / "mission-control.incoming.enc").write_bytes(b"tampered")

        with self.assertRaisesRegex(BackupArtifactError, "HMAC verification failed"):
            promote_incoming(self.root, self.key)

        self.assertEqual(current.read_bytes(), b"old")
        self.assertFalse((self.root / "mission-control.previous.enc").exists())

    def test_key_format_is_fixed_and_redacted(self):
        self.assertEqual(read_key(self.key), b"A" * 64)
        self.key.write_text("too-short\n", encoding="ascii")

        with self.assertRaisesRegex(BackupArtifactError, "invalid format"):
            read_key(self.key)


if __name__ == "__main__":
    unittest.main()
