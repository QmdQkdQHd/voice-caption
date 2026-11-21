"""Packaged-runtime check; does not record audio, capture screens or download models."""
import importlib
import json
import multiprocessing
from pathlib import Path
import platform
import time
import traceback


def probe(connection):
    phase = "starting"
    imported = []
    try:
        for name in ("numpy", "scipy.signal", "soundcard", "faster_whisper",
                     "ctranslate2", "argostranslate.translate", "mss", "pytesseract", "PySide6.QtWidgets"):
            phase = f"import:{name}"
            connection.send({"progress": True, "phase": phase, "imports": imported})
            importlib.import_module(name)
            imported.append(name)
        # Validates that bundled Silero VAD data and ONNX binaries are present.
        phase = "bundled_vad"
        connection.send({"progress": True, "phase": phase, "imports": imported})
        from faster_whisper.vad import get_vad_model
        get_vad_model()
        connection.send({"ok": True, "phase": "complete", "imports": imported,
                         "checks": ["imports", "bundled_vad", "spawn_ipc"]})
    except Exception as exc:
        connection.send({"ok": False, "phase": phase, "imports": imported,
                         "error": f"{type(exc).__name__}: {exc}",
                         "traceback": traceback.format_exc()})
    finally:
        connection.close()


def run(destination):
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=probe, args=(send,), daemon=True)
    result = {"ok": False, "phase": "spawn", "imports": [],
              "error": "Packaged self-test timed out (90s)"}
    started = time.monotonic()
    try:
        process.start()
        send.close()
        deadline = started + 90
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not receive.poll(remaining):
                break
            message = receive.recv()
            if not isinstance(message, dict):
                raise ValueError("Self-test worker returned an invalid message")
            if message.get("progress") is True:
                result.update(phase=message["phase"], imports=message["imports"])
                continue
            if not isinstance(message.get("ok"), bool):
                raise ValueError("Self-test worker returned a result without a boolean 'ok'")
            result = message
            break
    except Exception as exc:
        result.update(ok=False, error=f"{type(exc).__name__}: {exc}",
                      traceback=traceback.format_exc())
    finally:
        if process.pid is not None:
            process.join(5)
            if process.is_alive():
                result.update(ok=False, shutdown_error="Worker did not exit within 5 seconds; terminated")
                process.terminate()
                process.join(2)
            if process.is_alive():
                result["shutdown_error"] = "Worker did not terminate; killed"
                process.kill()
                process.join(1)
            result["worker_exitcode"] = process.exitcode
            if process.is_alive():
                result.update(ok=False, shutdown_error="Worker is still alive after kill")
            else:
                if process.exitcode != 0:
                    result["ok"] = False
                    result.setdefault("error", f"Self-test worker exited with code {process.exitcode}")
                process.close()
        receive.close()
        send.close()
    result["platform"] = platform.platform()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    Path(destination).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
