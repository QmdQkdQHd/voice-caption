"""Dependency-free timing and configuration helpers."""
from collections import deque
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from queue import Empty, Full
from threading import Lock


@dataclass
class Settings:
    source: str = "en"
    target: str = "ko"
    model: str = "tiny"
    seconds: int = 3
    threads: int = 2
    api_fallback: bool = False
    font: str = "Malgun Gothic"
    font_size: int = 26
    opacity: int = 65
    text_color: str = "#ffffff"
    show_original: bool = True
    expiry: int = 8
    x: int = 120
    y: int = 120
    width: int = 800
    height: int = 220
    ocr: bool = False
    roi: str = "0,0,400,200"
    active_color: str = "#23a55a"
    color_tolerance: int = 45
    ocr_language: str = "eng"
    tesseract_path: str = ""
    silence_ms: int = 500
    threshold_db: int = -42

    @classmethod
    def load(cls, path):
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("설정 파일은 JSON 객체여야 합니다.")
        obj = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        defaults = cls()
        for key, value in asdict(obj).items():
            if type(value) is not type(getattr(defaults, key)):
                raise ValueError(f"설정 형식 오류: {key}")
        for key, lo, hi in [("seconds", 2, 8), ("threads", 1, 8), ("font_size", 12, 72),
                            ("opacity", 0, 100), ("expiry", 2, 30),
                            ("width", 300, 2000), ("height", 100, 1000),
                            ("silence_ms", 200, 1500), ("threshold_db", -65, -15)]:
            setattr(obj, key, max(lo, min(hi, getattr(obj, key))))
        return obj

    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)


def settings_path():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".config"))) / "VoiceCaption" / "settings.json"


def put_latest(queue, item):
    """One producer; discard oldest pending work to keep latency bounded."""
    dropped = False
    while True:
        try:
            queue.put_nowait(item)
            return dropped
        except Full:
            try:
                queue.get_nowait()
                dropped = True
            except Empty:
                pass


class SpeakerTimeline:
    def __init__(self):
        self.samples = deque(maxlen=600)
        self.lock = Lock()

    def add(self, timestamp, names):
        with self.lock:
            self.samples.append((timestamp, frozenset(names)))

    def resolve(self, start, end):
        with self.lock:
            samples = [(ts, names) for ts, names in self.samples if start <= ts <= end]
        values = [names for _, names in samples]
        # Require repeated evidence, reject overlaps, gaps and name changes.
        if len(values) < 2 or any(len(names) != 1 for names in values):
            return "화자 미확인"
        times = [ts for ts, _ in samples]
        if times[0] - start > 0.8 or end - times[-1] > 0.8:
            return "화자 미확인"
        if any(b - a > 1.2 for a, b in zip(times, times[1:])):
            return "화자 미확인"
        names = set().union(*values)
        return next(iter(names)) + " (화면 추정)" if len(names) == 1 else "화자 미확인"


def parse_roi(value):
    parts = [int(x.strip()) for x in value.split(",")]
    if len(parts) != 4 or not 10 <= parts[2] <= 2000 or not 10 <= parts[3] <= 1200:
        raise ValueError("화면 영역은 왼쪽,위,너비,높이 형식이며 최소 10×10이어야 합니다.")
    return dict(zip(("left", "top", "width", "height"), parts))


class UtteranceBuffer:
    """100 ms frames; energy gate for endpointing, ASR performs speech VAD later.

    Keep 200 ms of pre-roll. Continuous sound is bounded by max_frames; no
    overlap is replayed, so a forced boundary may still split a word.
    """
    def __init__(self, max_frames=30, silence_frames=5):
        self.max_frames = max_frames
        self.silence_frames = silence_frames
        self.preroll = deque(maxlen=2)
        self.frames = []
        self.quiet = 0

    def feed(self, frame, active):
        if not self.frames:
            if not active:
                self.preroll.append(frame)
                return None
            self.frames = list(self.preroll)
            self.preroll.clear()
        self.frames.append(frame)
        self.quiet = 0 if active else self.quiet + 1
        if self.quiet >= self.silence_frames or len(self.frames) >= self.max_frames:
            result, self.frames = self.frames, []
            self.quiet = 0
            return result
        return None


class CaptionHistory:
    def __init__(self, limit=3):
        self.items = deque(maxlen=limit)

    def add(self, speaker, original, translated, now, minimum_seconds):
        self.prune(now)
        duration = max(minimum_seconds, min(20, len(translated) / 8 + 2))
        self.items.append((now + duration, speaker, original, translated))

    def prune(self, now):
        self.items = deque((x for x in self.items if x[0] > now), maxlen=self.items.maxlen)

    def clear(self):
        self.items.clear()
