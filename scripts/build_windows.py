"""Build, check and zip a Windows onedir bundle. No upload or publishing."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def check_packaged_runtime(bundle, *, integration_audio=None):
    """Show the windowed executable's report before failing the build."""
    label = "Packaged integration test" if integration_audio else "Packaged self-test"
    report = bundle / ("integration-test.json" if integration_audio else "self-test.json")
    arguments = (["--integration-test-report", str(report), "--audio-fixture", str(integration_audio)]
                 if integration_audio else ["--self-test-report", str(report)])
    timeout = 930 if integration_audio else 120
    report.unlink(missing_ok=True)
    failure = None
    try:
        completed = subprocess.run(
            [str(bundle / "VoiceCaption.exe"), *arguments],
            cwd=bundle, timeout=timeout, check=False,
        )
        if completed.returncode:
            failure = f"executable exited with code {completed.returncode}"
    except subprocess.TimeoutExpired:
        failure = f"executable timed out after {timeout} seconds"
    except OSError as exc:
        failure = f"could not start executable: {exc}"
    try:
        raw = report.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"{label} failed: {failure or 'executable finished'}; "
                         f"no report was created at {report}") from None
    except (OSError, UnicodeError) as exc:
        raise SystemExit(f"{label} report could not be read: {exc}; "
                         f"process: {failure or 'exit code 0'}") from None
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} produced invalid JSON at {report}: {exc}; "
                         f"process: {failure or 'exit code 0'}") from None
    # ASCII escaping also works with non-UTF-8 Windows build consoles.
    print(label + " report:\n" + json.dumps(result, indent=2, ensure_ascii=True), flush=True)
    if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
        raise SystemExit(f"{label} report must be an object with a boolean 'ok' field")
    if failure or not result["ok"]:
        raise SystemExit(f"{label} failed: {failure or result.get('error', 'ok=false')}; "
                         f"inspect {report}")


def main():
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("Windows x64 is required. This is not a cross-compilation script.")
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Use Python 3.11 x64 for this build.")
    audio_fixture = os.environ.get("VOICE_CAPTION_TEST_AUDIO")
    if audio_fixture:
        audio_fixture = Path(audio_fixture).expanduser().resolve()
        if not audio_fixture.is_file():
            raise SystemExit(f"VOICE_CAPTION_TEST_AUDIO does not point to a file: {audio_fixture}")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "packaging/VoiceCaption.spec"], cwd=ROOT, check=True)
    bundle = ROOT / "dist" / "VoiceCaption"
    check_packaged_runtime(bundle)
    subprocess.run([str(bundle / "VoiceCaption.exe"), "--smoke-test"], cwd=bundle,
                   timeout=30, check=True)
    if audio_fixture:
        check_packaged_runtime(bundle, integration_audio=audio_fixture)
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
