"""Build, check and zip a Windows onedir bundle. No upload or publishing."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("Windows x64 is required. This is not a cross-compilation script.")
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Use Python 3.11 x64 for this build.")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "packaging/VoiceCaption.spec"], cwd=ROOT, check=True)
    bundle = ROOT / "dist" / "VoiceCaption"
    report = bundle / "self-test.json"
    report.unlink(missing_ok=True)
    subprocess.run([str(bundle / "VoiceCaption.exe"), "--self-test-report", str(report)],
                   cwd=bundle, timeout=120, check=True)
    if not json.loads(report.read_text(encoding="utf-8")).get("ok"):
        raise SystemExit("Packaged self-test failed; inspect dist/VoiceCaption/self-test.json")
    subprocess.run([str(bundle / "VoiceCaption.exe"), "--smoke-test"], cwd=bundle,
                   timeout=30, check=True)
    for name in ("README.md", "read.md"):
        shutil.copy2(ROOT / name, bundle / name)
    shutil.copytree(ROOT / "docs", bundle / "docs", dirs_exist_ok=True)
    guide = (ROOT / "docs" / "친구용-사용설명서.html").read_text(encoding="utf-8")
    guide = guide.replace('src="settings-preview.png"', 'src="docs/settings-preview.png"')
    guide = guide.replace('src="subtitle-preview.png"', 'src="docs/subtitle-preview.png"')
    guide = guide.replace('href="../read.md"', 'href="read.md"')
    guide = guide.replace('href="VALIDATION.md"', 'href="docs/VALIDATION.md"')
    (bundle / "사용설명서.html").write_text(guide, encoding="utf-8")
    freeze = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
    # Exclude the editable application's machine-specific checkout path.
    freeze = "\n".join(line for line in freeze.splitlines() if not line.startswith(("-e ", "#")))
    (bundle / "build-dependencies.txt").write_text(freeze + "\n", encoding="utf-8")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    archive = Path(shutil.make_archive(str(release / f"VoiceCaption-{version}-windows-x64"),
                                       "zip", ROOT / "dist", "VoiceCaption"))
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Created: {archive}")


if __name__ == "__main__":
    main()
