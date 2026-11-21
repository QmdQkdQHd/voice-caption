"""Opt-in frozen model test using a supplied WAV; never captures audio or screens."""
import json
import multiprocessing
import os
from pathlib import Path
import platform
import re
import sys
import time
import traceback


def _runtime_paths(fixture):
    return {
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "bundle_root": getattr(sys, "_MEIPASS", None),
        "working_directory": str(Path.cwd()),
        "audio_fixture": str(Path(fixture).resolve()),
        "python": sys.version,
        "platform": platform.platform(),
    }


def _watch_network(block):
    """Process-local Python audit guard; HF offline flags cover its native downloader."""
    attempts = []

    def audit(event, args):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
                     "socket.gethostbyaddr", "socket.sendto", "http.client.connect"}:
            attempts.append(event)
            if block:
                raise RuntimeError(f"Network is disabled during offline integration test: {event}")

    sys.addaudithook(audit)
    return attempts


def _validate_transcript(text):
    if not text.strip() or not re.search(r"\b(hello|team|ready)\b", text, re.IGNORECASE):
        raise AssertionError(f"Expected English fixture keywords (hello/team/ready), got: {text!r}")


def _validate_translation(source, translated, backend):
    if backend != "로컬" or not translated.strip() or translated.strip() == source.strip():
        raise AssertionError(f"Expected distinct local translation, got backend={backend!r}, text={translated!r}")
    if not re.search(r"[\uac00-\ud7a3]", translated):
        raise AssertionError(f"Expected Korean text, got: {translated!r}")


def _probe(connection, fixture, offline):
    phase = "starting"
    result = {"ok": False, "runtime": _runtime_paths(fixture), "offline": offline}
    attempts = []

    def progress(value, detail=None):
        nonlocal phase
        phase = value
        connection.send({"progress": True, "phase": phase, "detail": detail})

    try:
        os.environ["ARGOS_DEVICE_TYPE"] = "cpu"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["DO_NOT_TRACK"] = "1"
        os.environ.pop("DEEPL_AUTH_KEY", None)
        if offline:
            for variable in ("HF_HUB_OFFLINE", "HF_DATASETS_OFFLINE", "TRANSFORMERS_OFFLINE"):
                os.environ[variable] = "1"
            attempts = _watch_network(block=True)
        else:
            from .models import prepare
            progress("model_download")
            prepare("en", "ko", "tiny", lambda detail: progress("model_download", detail))
            # Record lazy first-use downloads separately from explicit preparation.
            attempts = _watch_network(block=False)

        progress("offline_imports" if offline else "warmup_imports")
        import argostranslate.package as package
        import faster_whisper
        from huggingface_hub.constants import HF_HUB_CACHE
        from .core import Settings
        from .pipeline import Translator

        result["runtime"].update(
            whisper_module=faster_whisper.__file__,
            argos_module=package.__file__,
            huggingface_cache=str(HF_HUB_CACHE),
            translation_packages=[{"from": item.from_code, "to": item.to_code,
                                   "path": str(getattr(item, "package_path", "unknown"))}
                                  for item in package.get_installed_packages()],
        )
        prefix = "offline" if offline else "warmup"
        progress(f"{prefix}_whisper_load")
        model = faster_whisper.WhisperModel("tiny", device="cpu", compute_type="int8",
                                           cpu_threads=2, num_workers=1, local_files_only=True)
        progress(f"{prefix}_speech_recognition")
        segments, _ = model.transcribe(fixture, language="en", beam_size=1,
                                       vad_filter=True, condition_on_previous_text=False)
        result["transcript"] = " ".join(segment.text.strip() for segment in segments).strip()
        _validate_transcript(result["transcript"])
        progress(f"{prefix}_local_translation")
        translator = Translator(Settings(source="en", target="ko", api_fallback=False))
        translated, backend = translator.translate(result["transcript"])
        result.update(translation=translated, translation_backend=backend)
        _validate_translation(result["transcript"], translated, backend)
        if offline and attempts:
            raise AssertionError("An offline library attempted network access, even though the guard blocked it")
        result.update(ok=True, phase="complete")
    except Exception as exc:
        result.update(phase=phase, error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    finally:
        result["network_attempt_count"] = len(attempts)
        result["network_events"] = attempts[:20]
        connection.send(result)
        connection.close()


def _run_stage(fixture, offline, timeout):
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_probe, args=(send, fixture, offline), daemon=True)
    result = {"ok": False, "phase": "spawn", "error": "Integration test time budget exceeded"}
    progress = []
    started = time.monotonic()
    try:
        process.start()
        send.close()
        deadline = started + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not receive.poll(remaining):
                break
            message = receive.recv()
            if not isinstance(message, dict):
                raise ValueError("Integration worker returned an invalid message")
            if message.get("progress") is True:
                result["phase"] = message["phase"]
                progress.append({"phase": message["phase"], "detail": message.get("detail"),
                                 "elapsed_seconds": round(time.monotonic() - started, 3)})
                continue
            if not isinstance(message.get("ok"), bool):
                raise ValueError("Integration worker result lacks a boolean 'ok' field")
            result = message
            break
    except Exception as exc:
        result.update(ok=False, error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
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
                    result.setdefault("error", f"Integration worker exited with code {process.exitcode}")
                process.close()
        receive.close()
        send.close()
    result.update(progress=progress, elapsed_seconds=round(time.monotonic() - started, 3))
    return result


def run(destination, audio_fixture):
    started = time.monotonic()
    fixture = str(Path(audio_fixture).resolve())
    report = {"ok": False, "runtime": _runtime_paths(fixture), "stages": {},
              "network_guard": "Python network audit hooks plus HF offline flags; not an OS firewall",
              "scope": "Supplied WAV only; no live audio or screen capture; en to ko; tiny CPU int8"}
    try:
        if not Path(fixture).is_file():
            raise FileNotFoundError(f"Audio fixture does not exist: {fixture}")
        for name, offline in (("prepare_and_warmup", False), ("fresh_process_offline", True)):
            remaining = 900 - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Integration test exceeded its total 15-minute budget")
            result = _run_stage(fixture, offline, remaining)
            report["stages"][name] = result
            if not result["ok"]:
                report.update(phase=result["phase"], error=f"{name} failed; inspect the stage report")
                break
        else:
            report.update(ok=True, phase="complete")
    except Exception as exc:
        report.update(phase="setup", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    Path(destination).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
