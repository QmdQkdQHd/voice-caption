"""Allowlisted source archive; never includes virtualenvs, keys or recordings."""
import hashlib
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package(root=ROOT):
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    paths = [root / name for name in ("pyproject.toml", "README.md", "read.md", ".gitignore",
             "install-windows.cmd", "start-windows.cmd", "build-windows.cmd")]
    allowed = {"voice_caption": {".py"}, "tests": {".py"}, "scripts": {".py", ".ps1"},
               "packaging": {".py", ".spec", ".txt"}, "docs": {".md", ".png", ".html"}}
    allowed[".github/workflows"] = {".yml", ".yaml"}
    for directory, extensions in allowed.items():
        paths.extend(p for p in (root / directory).rglob("*") if p.is_file()
                     and p.suffix in extensions and "__pycache__" not in p.parts)
    release = root / "release"
    release.mkdir(exist_ok=True)
    archive = release / f"VoiceCaption-{version}-source.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for path in sorted(paths):
            if path.is_symlink():
                raise ValueError(f"Symlink cannot be packaged: {path}")
            output.write(path, Path("voice-caption") / path.relative_to(root))
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return archive


if __name__ == "__main__":
    print(package())
