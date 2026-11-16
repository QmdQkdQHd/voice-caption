"""Audio and inference live in a disposable child process, never in the UI process."""
import json
import os
from queue import Empty, Queue
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .core import SpeakerTimeline, UtteranceBuffer, put_latest, parse_roi


class Translator:
    def __init__(self, settings):
        self.settings = settings
        self.local = None
        if settings.source == settings.target:
            return
        os.environ["ARGOS_DEVICE_TYPE"] = "cpu"
        import argostranslate.translate as translate
        languages = {lang.code: lang for lang in translate.get_installed_languages()}
        if settings.source in languages and settings.target in languages:
            try:
                self.local = languages[settings.source].get_translation(languages[settings.target])
            except Exception:
                pass
        if self.local is None and not settings.api_fallback:
            raise RuntimeError("번역 모델이 없습니다. 먼저 ‘모델 준비’를 실행하세요.")

    def translate(self, text):
        cfg = self.settings
        if cfg.source == cfg.target:
            return text, "원문"
        if self.local is not None:
            try:
                return self.local.translate(text), "로컬"
            except Exception:
                if not cfg.api_fallback:
                    raise RuntimeError("로컬 번역 실패. 모델 설치 상태를 확인하세요.") from None
        if not cfg.api_fallback:
            raise RuntimeError("로컬 번역 모델이 없습니다.")
        key = os.environ.get("DEEPL_AUTH_KEY", "").strip()
        if not key:
            raise RuntimeError("API 사용을 선택했지만 DEEPL_AUTH_KEY 환경 변수가 없습니다.")
        host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
        target = {"en": "EN-US", "pt": "PT-PT"}.get(cfg.target, cfg.target.upper())
        payload = json.dumps({"text": [text], "source_lang": cfg.source.upper(), "target_lang": target}).encode()
        req = Request(f"https://{host}/v2/translate", data=payload,
                      headers={"Authorization": f"DeepL-Auth-Key {key}", "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=8) as response:
                return json.load(response)["translations"][0]["text"], "DeepL API"
        except HTTPError as exc:
            raise RuntimeError(f"DeepL 요청 실패 (HTTP {exc.code}). 키·한도·지원 언어를 확인하세요.") from None
        except (URLError, TimeoutError):
            raise RuntimeError("DeepL 연결 실패 또는 시간 초과") from None


def capture(device_id, settings, stop, queue, status):
    import numpy as np
    import soundcard as sc
    from scipy.signal import resample_poly
    # The backend is created inside its owning thread (WASAPI/COM).
    device = sc.get_microphone(id=device_id, include_loopback=True)
    buffer = UtteranceBuffer(settings.seconds * 10, (settings.silence_ms + 99) // 100)
    # Capture all channels: SoundCard documents a Windows single-channel issue.
    with device.recorder(samplerate=48000, blocksize=4800) as recorder:
        while not stop.is_set():
            block = recorder.record(numframes=4800)
            end = time.monotonic()
            mono = block.mean(axis=1)
            rms = float(np.sqrt(np.mean(mono ** 2)))
            active = rms >= 10 ** (settings.threshold_db / 20)
            frames = buffer.feed((end - len(block) / 48000, mono), active)
            if frames:
                start = frames[0][0]
                raw = np.concatenate([samples for _, samples in frames])
                audio = resample_poly(raw, 1, 3).astype(np.float32)
                if put_latest(queue, (start, end, audio)):
                    status("처리가 밀려 오래된 음성을 건너뛰었습니다. 더 작은 모델을 선택하세요.")


def watch_speakers(settings, stop, timeline):
    """Experimental color-row OCR; only captures the user-configured region."""
    import mss
    import numpy as np
    from PIL import Image
    import pytesseract
    if settings.tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_path
    roi = parse_roi(settings.roi)
    rgb = np.array([int(settings.active_color[i:i + 2], 16) for i in (1, 3, 5)])
    with mss.mss() as screen:
        while not stop.is_set():
            timestamp = time.monotonic()
            frame = np.asarray(screen.grab(roi))[:, :, :3][:, :, ::-1].copy()
            mask = np.max(np.abs(frame.astype(int) - rgb), axis=2) <= settings.color_tolerance
            rows = np.where(mask.sum(axis=1) >= 3)[0]
            names = set()
            if len(rows):
                groups = np.split(rows, np.where(np.diff(rows) > 12)[0] + 1)
                for group in groups:
                    if stop.is_set():
                        return
                    top, bottom = max(0, int(group[0]) - 6), min(len(frame), int(group[-1]) + 7)
                    crop = Image.fromarray(frame[top:bottom]).resize((frame.shape[1] * 2, (bottom - top) * 2))
                    data = pytesseract.image_to_data(crop, lang=settings.ocr_language,
                                                    config="--psm 7", timeout=2,
                                                    output_type=pytesseract.Output.DICT)
                    words = [word.strip() for word, conf in zip(data["text"], data["conf"])
                             if float(conf) >= 65 and word.strip()]
                    name = " ".join(words)
                    if 1 < len(name) <= 50:
                        names.add(name)
                    else:
                        # Any unreadable active row makes this observation ambiguous.
                        names.clear()
                        break
            timeline.add(timestamp, names)
            stop.wait(0.4)



def translate_pending(settings, stop, pending, emit, translator_factory=Translator, clock=time.monotonic):
    """Independent translation consumer; expire results both before and after I/O."""
    try:
        translator = translator_factory(settings)
    except Exception as exc:
        emit("error", f"번역 초기화 실패: {exc}")
        stop.set()
        return
    while not stop.is_set():
        try:
            end, speaker, original = pending.get(timeout=0.1)
        except Empty:
            continue
        if clock() - end > 12:
            emit("status", "오래된 번역 요청을 건너뛰었습니다.")
            continue
        try:
            translated, backend = translator.translate(original)
        except Exception as exc:
            emit("error", f"번역 실패: {exc}")
            translated, backend = "[번역 실패] " + original, "실패"
        if stop.is_set():
            return
        if clock() - end > 12:
            emit("status", "늦게 도착한 번역 결과를 건너뛰었습니다.")
            continue
        emit("caption", speaker, original, translated)
        emit("status", f"듣는 중 · {backend} · 구간 종료 후 {clock() - end:.1f}초")


def pipeline_main(settings, device_id, stop, events):
    """Spawn target. Termination is owned by the parent process supervisor."""
    def emit(kind, *values):
        # Bounded IPC; old status/caption events must not hold up audio work.
        put_latest(events, (kind, values))

    try:
        from faster_whisper import WhisperModel
        emit("status", "CPU 음성 모델을 불러오는 중…")
        model = WhisperModel(settings.model, device="cpu", compute_type="int8",
                             cpu_threads=settings.threads, num_workers=1, local_files_only=True)
        if stop.is_set():
            return
        audio_queue, pending = Queue(maxsize=2), Queue(maxsize=3)
        timeline = SpeakerTimeline()

        def record():
            try:
                capture(device_id, settings, stop, audio_queue, lambda msg: emit("status", msg))
            except Exception as exc:
                emit("error", f"오디오 캡처 실패: {exc}")
                stop.set()

        def observe():
            try:
                watch_speakers(settings, stop, timeline)
            except Exception as exc:
                timeline.add(time.monotonic(), set())
                emit("error", f"화면 화자 인식 중단: {exc}")

        threading.Thread(target=record, daemon=True).start()
        if settings.ocr:
            threading.Thread(target=observe, daemon=True).start()
        translation = threading.Thread(target=translate_pending,
                                       args=(settings, stop, pending, emit), daemon=True)
        translation.start()
        emit("status", "듣는 중 · CPU / 무음 구간 분할 / 로컬 우선")
        while not stop.is_set():
            try:
                start, end, audio = audio_queue.get(timeout=0.1)
            except Empty:
                continue
            if time.monotonic() - end > 8:
                emit("status", "오래된 음성을 건너뛰었습니다.")
                continue
            segments, _ = model.transcribe(audio, language=settings.source, beam_size=1,
                                           vad_filter=True, condition_on_previous_text=False)
            for segment in segments:
                if stop.is_set():
                    break
                original = segment.text.strip()
                if original:
                    speaker = timeline.resolve(start + segment.start, start + segment.end)
                    if put_latest(pending, (end, speaker, original)):
                        emit("status", "번역이 밀려 오래된 대기 문장을 건너뛰었습니다.")
    except Exception as exc:
        emit("error", str(exc))
    finally:
        stop.set()
        # Flush fatal errors on normal exit. The supervisor still bounds shutdown
        # if a stopped parent no longer drains the queue.
        events.close()
        events.join_thread()
