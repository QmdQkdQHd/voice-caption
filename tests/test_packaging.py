import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from scripts.package_source import package


class SourcePackageTests(unittest.TestCase):
    def test_source_archive_excludes_private_data_and_has_valid_checksum(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n')
            for name in ("README.md", "read.md", ".gitignore", "install-windows.cmd",
                         "start-windows.cmd", "build-windows.cmd"):
                (root / name).write_text("test")
            for name in (".env", "settings.json", ".venv/lib/secret.py",
                         "recordings/private.wav", "models/private.bin", "voice_caption/app.py",
                         "docs/친구용-사용설명서.html"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            archive = package(root)
            with zipfile.ZipFile(archive) as bundle:
                self.assertIsNone(bundle.testzip())
                names = set(bundle.namelist())
            self.assertIn("voice-caption/voice_caption/app.py", names)
            self.assertIn("voice-caption/read.md", names)
            self.assertIn("voice-caption/docs/친구용-사용설명서.html", names)
            for forbidden in (".env", "settings.json", ".venv", "recordings", "models"):
                self.assertFalse(any(forbidden in Path(name).parts for name in names))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(archive.with_suffix(".zip.sha256").read_text().split()[0], digest)


if __name__ == "__main__":
    unittest.main()
