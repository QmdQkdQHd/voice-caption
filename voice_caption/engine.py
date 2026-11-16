import sys
import threading

from PySide6.QtCore import QThread, Signal

from .pipeline import pipeline_main
from .runtime import supervise


class Engine(QThread):
    caption = Signal(str, str, str)
    status = Signal(str)
    failed = Signal(str)

    def __init__(self, settings, device_id):
        super().__init__()
        self.settings = settings
        self.device_id = device_id
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        if sys.platform != "win32":
            self.failed.emit("실제 오디오 캡처는 Windows에서 실행하세요.")
            return
        def dispatch(kind, values):
            if kind == "caption":
                self.caption.emit(*values)
            elif kind == "error":
                self.failed.emit(*values)
            else:
                self.status.emit(*values)
        try:
            supervise(pipeline_main, (self.settings, self.device_id), self.stop_event, dispatch)
        except Exception as exc:
            self.failed.emit(str(exc))


class ModelInstaller(QThread):
    status = Signal(str)
    failed = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def run(self):
        try:
            from .models import prepare
            prepare(self.settings.source, self.settings.target, self.settings.model, self.status.emit)
            self.status.emit("모델 준비 완료. 시작을 누르세요.")
        except Exception as exc:
            self.failed.emit(f"모델 준비 실패: {exc}")
