# Windows-only onedir build; models and Tesseract are provisioned separately.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

if sys.platform != "win32":
    raise SystemExit("Build VoiceCaption.exe on Windows 10/11 x64 with Python 3.11.")

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = [], [], []
for package in ("faster_whisper", "ctranslate2", "argostranslate", "soundcard",
                "stanza", "sentencepiece", "tokenizers", "onnxruntime", "av"):
    data, binary, hidden = collect_all(package)
    datas.extend(data)
    binaries.extend(binary)
    hiddenimports.extend(hidden)
for distribution in ("faster-whisper", "argostranslate"):
    datas.extend(copy_metadata(distribution, recursive=True))

a = Analysis(
    [str(root / "packaging" / "launcher.py")], pathex=[str(root)],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VoiceCaption",
          debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VoiceCaption")
