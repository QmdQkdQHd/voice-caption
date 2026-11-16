"""Packaged-runtime check; does not record audio, capture screens or download models."""
import importlib
import json
import multiprocessing
from pathlib import Path
import platform


def probe(connection):
    try:
        for name in ("numpy", "scipy.signal", "soundcard", "faster_whisper",
                     "ctranslate2", "argostranslate.translate", "mss", "pytesseract", "PySide6.QtWidgets"):
            importlib.import_module(name)
        # Validates that bundled Silero VAD data and ONNX binaries are present.
        from faster_whisper.vad import get_vad_model
        get_vad_model()
        connection.send({"ok": True, "checks": ["imports", "bundled_vad", "spawn_ipc"]})
    except Exception as exc:
        connection.send({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        connection.close()


def run(destination):
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=probe, args=(send,))
    result = {"ok": False, "error": "Packaged self-test timed out (90s)"}
    try:
        process.start()
        send.close()
        if receive.poll(90):
            result = receive.recv()
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if process.pid is not None:
            process.join(1)
            if process.is_alive():
                process.terminate()
                process.join(2)
            if process.is_alive():
                process.kill()
                process.join(1)
        receive.close()
        send.close()
    result["platform"] = platform.platform()
    Path(destination).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
