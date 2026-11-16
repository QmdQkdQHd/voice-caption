import argparse
from dataclasses import replace
import sys
import time

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QFontComboBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizeGrip, QSpinBox,
    QVBoxLayout, QWidget,
)

from .core import CaptionHistory, Settings, parse_roi, settings_path
from .engine import Engine, ModelInstaller


class Overlay(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.cfg = settings
        self.drag_offset = None
        self.locked = False
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMinimumSize(300, 100)
        self.setGeometry(settings.x, settings.y, settings.width, settings.height)
        if not any(screen.availableGeometry().intersects(self.geometry()) for screen in QApplication.screens()):
            self.move(QApplication.primaryScreen().availableGeometry().topLeft() + QPoint(40, 40))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 8)
        self.history = CaptionHistory()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea, QWidget { background: transparent; border: none; }")
        content = QWidget()
        rows = QVBoxLayout(content)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cards = []
        for _ in range(3):
            card = QWidget()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(0, 0, 0, 6)
            labels = [QLabel() for _ in range(3)]
            for label in labels:
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setWordWrap(True)
                label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                card_layout.addWidget(label)
            rows.addWidget(card)
            self.cards.append((card, *labels))
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll)
        footer = QHBoxLayout()
        self.hint = QLabel("테두리 드래그로 이동 · 오른쪽 아래로 크기 조절 · 최근 3개 발화")
        self.hint.setStyleSheet("color: #a1acc4; font-size: 11px;")
        self.hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        footer.addWidget(self.hint)
        self.grip = QSizeGrip(self)
        footer.addWidget(self.grip, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(footer)
        self.expiry = QTimer(self)
        self.expiry.setInterval(200)
        self.expiry.timeout.connect(self.expire_captions)
        self.expiry.start()
        self.apply(settings)
        self.display("자막 미리보기", "Translated speech appears here.", "번역된 대화가 여기에 표시됩니다.")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(13, 18, 30, round(self.cfg.opacity * 2.55)))
        painter.drawRoundedRect(self.rect(), 14, 14)

    def apply(self, settings):
        self.cfg = settings
        for _, speaker, translated, original in self.cards:
            translated.setFont(QFont(settings.font, settings.font_size))
            original.setFont(QFont(settings.font, max(10, settings.font_size - 8)))
            speaker.setFont(QFont(settings.font, 11))
            speaker.setStyleSheet("color: #8be6ce;")
            translated.setStyleSheet(f"color: {settings.text_color};")
            original.setStyleSheet("color: #bdc7da;")
            original.setVisible(settings.show_original)
        self.update()

    def display(self, speaker, original, translated):
        self.history.add(speaker, original, translated, time.monotonic(), self.cfg.expiry)
        self.render_history()
        QTimer.singleShot(0, self.scroll_to_latest)

    def scroll_to_latest(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def render_history(self):
        for index, (card, speaker, translated, original) in enumerate(self.cards):
            card.setVisible(index < len(self.history.items))
            if index < len(self.history.items):
                _, name, source, text = self.history.items[index]
                speaker.setText(name)
                original.setText(source)
                translated.setText(text)

    def expire_captions(self):
        before = len(self.history.items)
        self.history.prune(time.monotonic())
        if before != len(self.history.items):
            self.render_history()

    def clear_caption(self):
        self.history.clear()
        self.render_history()

    def set_locked(self, locked):
        self.locked = locked
        self.drag_offset = None
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, locked)
        self.hint.setVisible(not locked)
        self.grip.setVisible(not locked)
        if visible:
            self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.locked:
            self.drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        self.drag_offset = None


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voice Caption · 로컬 음성 번역")
        self.resize(600, 850)
        self.load_error = ""
        try:
            self.cfg = Settings.load(settings_path())
        except (OSError, ValueError, TypeError) as exc:
            self.cfg = Settings()
            self.load_error = f"설정을 읽지 못해 기본값으로 시작했습니다: {exc}"
        families = QFontDatabase.families()
        if self.cfg.font not in families:
            preferred = ["Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Arial"]
            self.cfg.font = next((font for font in preferred if font in families), families[0])
        self.engine = None
        self.installer = None
        self.closing = False
        self.overlay = Overlay(self.cfg)
        self.overlay.show()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        title = QLabel("VOICE CAPTION")
        title.setStyleSheet("font-size: 25px; font-weight: 700; color: #8be6ce;")
        layout.addWidget(title)
        subtitle = QLabel("게임과 대화를, 내 언어로.\nCPU 로컬 처리 · Windows 10/11용 개발 버전")
        layout.addWidget(subtitle)

        self.audio_box = QGroupBox("음성 및 번역")
        form = QFormLayout(self.audio_box)
        self.devices = QComboBox()
        refresh = QPushButton("장치 새로고침")
        refresh.clicked.connect(self.refresh_devices)
        form.addRow("받아올 소리", self.devices)
        form.addRow(refresh)
        self.source = self.language_combo(self.cfg.source)
        self.target = self.language_combo(self.cfg.target)
        form.addRow("원문 언어", self.source)
        form.addRow("번역 언어", self.target)
        self.model = QComboBox()
        self.model.addItems(["tiny", "base", "small"])
        self.model.setCurrentText(self.cfg.model)
        form.addRow("음성 모델 (작을수록 가벼움)", self.model)
        self.seconds = self.spin(2, 8, self.cfg.seconds)
        self.threads = self.spin(1, 8, self.cfg.threads)
        form.addRow("연속 소리 최대 길이 (초)", self.seconds)
        self.silence = self.spin(200, 1500, self.cfg.silence_ms)
        self.silence.setSingleStep(100)
        self.threshold = self.spin(-65, -15, self.cfg.threshold_db)
        form.addRow("발화 종료 무음 길이 (ms)", self.silence)
        form.addRow("무음 기준 (dBFS)", self.threshold)
        form.addRow("음성 인식 CPU 스레드", self.threads)
        self.api = QCheckBox("로컬 번역 실패 시 DeepL API 사용")
        self.api.setChecked(self.cfg.api_fallback)
        self.api.setToolTip("선택하면 인식한 텍스트를 DeepL로 전송합니다. DEEPL_AUTH_KEY 환경 변수가 필요하며 비용이 발생할 수 있습니다.")
        form.addRow(self.api)
        api_note = QLabel("API 선택 시 인식한 텍스트가 DeepL로 전송됩니다.\n키는 DEEPL_AUTH_KEY 환경 변수에서 읽습니다.")
        api_note.setWordWrap(True)
        form.addRow(api_note)
        layout.addWidget(self.audio_box)

        appearance = QGroupBox("자막 모양 · 즉시 반영")
        form = QFormLayout(appearance)
        self.font = QFontComboBox()
        self.font.setCurrentFont(QFont(self.cfg.font))
        self.size = self.spin(12, 72, self.cfg.font_size)
        self.opacity = self.spin(0, 100, self.cfg.opacity)
        self.expiry = self.spin(2, 30, self.cfg.expiry)
        self.width = self.spin(300, 2000, self.cfg.width)
        self.height = self.spin(100, 1000, self.cfg.height)
        self.original = QCheckBox("원문도 표시")
        self.original.setChecked(self.cfg.show_original)
        self.lock = QCheckBox("게임 조작 모드 · 자막 클릭 통과")
        self.lock.toggled.connect(self.overlay.set_locked)
        self.visible = QCheckBox("자막 창 표시")
        self.visible.setChecked(True)
        self.visible.toggled.connect(self.overlay.setVisible)
        self.color = QPushButton("글자 색 선택")
        self.color.clicked.connect(self.choose_text_color)
        for label, widget in [("폰트", self.font), ("글자 크기", self.size), ("배경 불투명도 (%)", self.opacity),
                              ("자막 최소 유지 (초)", self.expiry), ("창 너비", self.width), ("창 높이", self.height)]:
            form.addRow(label, widget)
        for widget in (self.color, self.original, self.lock, self.visible):
            form.addRow(widget)
        self.font.currentFontChanged.connect(self.apply_appearance)
        for widget in (self.size, self.opacity, self.expiry):
            widget.valueChanged.connect(self.apply_appearance)
        self.original.toggled.connect(self.apply_appearance)
        self.width.valueChanged.connect(self.resize_overlay)
        self.height.valueChanged.connect(self.resize_overlay)
        preview = QPushButton("예시 자막 표시")
        preview.clicked.connect(lambda: self.overlay.display("플레이어 A · 예시", "Two enemies at B. Let's go together.", "B에 적 두 명 있어. 같이 가자."))
        form.addRow(preview)
        layout.addWidget(appearance)

        self.ocr_box = QGroupBox("화면 화자 인식 · 실험적")
        form = QFormLayout(self.ocr_box)
        self.ocr = QCheckBox("발화 표시 색상과 닉네임 읽기")
        self.ocr.setChecked(self.cfg.ocr)
        self.roi = QLineEdit(self.cfg.roi)
        self.active_color = QLineEdit(self.cfg.active_color)
        self.ocr_language = QLineEdit(self.cfg.ocr_language)
        self.tesseract = QLineEdit(self.cfg.tesseract_path)
        self.tesseract.setPlaceholderText(r"선택 사항: C:\Program Files\Tesseract-OCR\tesseract.exe")
        form.addRow(self.ocr)
        form.addRow("영역: 왼쪽,위,너비,높이 (실제 픽셀)", self.roi)
        form.addRow("발화 표시 색 (#RRGGBB)", self.active_color)
        form.addRow("OCR 언어 (예: eng+kor)", self.ocr_language)
        form.addRow("Tesseract 실행 파일", self.tesseract)
        note = QLabel("발화 표시와 닉네임만 포함하는 작은 영역을 지정하세요.\nTesseract 별도 설치 필요. 동시 발화·판독 실패 시 화자 미확인으로 표시합니다.\n앱/게임별 화면 검증 전이며, 이름은 화면을 바탕으로 한 추정입니다.")
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(self.ocr_box)

        controls = QHBoxLayout()
        self.download = QPushButton("모델 준비 (최초 다운로드)")
        self.download.clicked.connect(self.install_models)
        self.start = QPushButton("시작")
        self.start.clicked.connect(self.start_engine)
        self.stop = QPushButton("중지")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.stop_engine)
        for widget in (self.download, self.start, self.stop):
            controls.addWidget(widget)
        self.status = QLabel("모델 준비 → 출력 장치 선택 → 시작")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        scroll.setWidget(body)
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(scroll)
        central_layout.addLayout(controls)
        central_layout.addWidget(self.status)
        error_row = QHBoxLayout()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #ffb4a8;")
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        error_row.addWidget(self.error_label, 1)
        clear_error = QPushButton("오류 지우기")
        clear_error.clicked.connect(self.error_label.clear)
        error_row.addWidget(clear_error)
        central_layout.addLayout(error_row)
        self.setCentralWidget(central)
        self.refresh_devices()
        if self.load_error:
            self.status.setText(self.load_error)

    @staticmethod
    def spin(minimum, maximum, value):
        box = QSpinBox()
        box.setRange(minimum, maximum)
        box.setValue(value)
        return box

    @staticmethod
    def language_combo(selected):
        combo = QComboBox()
        for code, name in [("en", "영어"), ("ko", "한국어"), ("ja", "일본어"), ("zh", "중국어"),
                           ("es", "스페인어"), ("fr", "프랑스어"), ("de", "독일어")]:
            combo.addItem(name, code)
        combo.setCurrentIndex(max(0, combo.findData(selected)))
        return combo

    def refresh_devices(self):
        self.devices.clear()
        if sys.platform != "win32":
            self.devices.addItem("Windows에서 장치 목록을 사용할 수 있습니다", None)
            return
        try:
            import soundcard as sc
            for device in sc.all_microphones(include_loopback=True):
                kind = "PC 소리" if device.isloopback else "마이크"
                self.devices.addItem(f"[{kind}] {device.name}", device.id)
            # Prefer loopback instead of accidentally recording the microphone.
            for index in range(self.devices.count()):
                if self.devices.itemText(index).startswith("[PC 소리]"):
                    self.devices.setCurrentIndex(index)
                    break
        except Exception as exc:
            self.status.setText(f"오디오 장치를 읽지 못했습니다: {exc}")

    def apply_appearance(self, *_):
        self.cfg.font = self.font.currentFont().family()
        self.cfg.font_size = self.size.value()
        self.cfg.opacity = self.opacity.value()
        self.cfg.expiry = self.expiry.value()
        self.cfg.show_original = self.original.isChecked()
        self.overlay.apply(self.cfg)

    def resize_overlay(self, *_):
        self.overlay.resize(self.width.value(), self.height.value())

    def choose_text_color(self):
        color = QColorDialog.getColor(QColor(self.cfg.text_color), self)
        if color.isValid():
            self.cfg.text_color = color.name()
            self.apply_appearance()

    def collect(self):
        self.cfg.source, self.cfg.target = self.source.currentData(), self.target.currentData()
        self.cfg.model = self.model.currentText()
        self.cfg.seconds, self.cfg.threads = self.seconds.value(), self.threads.value()
        self.cfg.silence_ms, self.cfg.threshold_db = self.silence.value(), self.threshold.value()
        self.cfg.api_fallback = self.api.isChecked()
        self.cfg.ocr, self.cfg.roi = self.ocr.isChecked(), self.roi.text().strip()
        self.cfg.active_color = self.active_color.text().strip()
        self.cfg.ocr_language = self.ocr_language.text().strip()
        self.cfg.tesseract_path = self.tesseract.text().strip()
        self.cfg.x, self.cfg.y = self.overlay.x(), self.overlay.y()
        self.cfg.width, self.cfg.height = self.overlay.width(), self.overlay.height()
        self.cfg.save(settings_path())
        return replace(self.cfg)

    def busy(self, busy):
        for widget in (self.audio_box, self.ocr_box, self.start, self.download):
            widget.setEnabled(not busy)

    def error(self, message):
        self.error_label.setText(message)

    def install_models(self):
        try:
            cfg = self.collect()
        except Exception as exc:
            self.error(str(exc))
            return
        self.busy(True)
        self.installer = ModelInstaller(cfg)
        self.installer.status.connect(self.status.setText)
        self.installer.failed.connect(self.error)
        self.installer.finished.connect(self.install_finished)
        self.installer.start()

    def install_finished(self):
        self.installer.deleteLater()
        self.installer = None
        self.busy(False)

    def start_engine(self):
        try:
            cfg = self.collect()
            if self.devices.currentData() is None:
                raise ValueError("Windows에서 입력 장치를 선택하세요.")
            if cfg.ocr:
                parse_roi(cfg.roi)
                if len(cfg.active_color) != 7 or not QColor(cfg.active_color).isValid():
                    raise ValueError("발화 표시 색을 #RRGGBB 형식으로 입력하세요.")
                if not cfg.ocr_language:
                    raise ValueError("OCR 언어를 입력하세요.")
            self.engine = Engine(cfg, self.devices.currentData())
            self.engine.caption.connect(self.receive_caption)
            self.engine.status.connect(self.status.setText)
            self.engine.failed.connect(self.error)
            self.engine.finished.connect(self.engine_finished)
            self.busy(True)
            self.stop.setEnabled(True)
            self.overlay.clear_caption()
            self.engine.start()
        except Exception as exc:
            self.error(str(exc))

    def stop_engine(self):
        if self.engine:
            self.engine.stop()
            self.stop.setEnabled(False)
            self.status.setText("중지 중… 응답 없는 작업도 종료합니다.")

    def receive_caption(self, speaker, original, translated):
        if self.engine is not None and not self.engine.stop_event.is_set():
            self.overlay.display(speaker, original, translated)

    def engine_finished(self):
        self.engine.deleteLater()
        self.engine = None
        self.busy(False)
        self.stop.setEnabled(False)
        self.status.setText("중지됨")
        if self.closing:
            self.close()

    def closeEvent(self, event):
        if self.installer is not None:
            QMessageBox.information(self, "모델 준비 중", "모델 다운로드가 끝나면 창을 닫을 수 있습니다.")
            event.ignore()
            return
        if self.engine is not None:
            self.closing = True
            self.stop_engine()
            event.ignore()
            return
        try:
            self.collect()
        except OSError as exc:
            QMessageBox.warning(self, "설정 저장 실패", str(exc))
        self.overlay.close()
        event.accept()


def configure_theme(app):
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow, QScrollArea, QWidget { background: #131a28; color: #e6edf8; }
        QGroupBox { border: 1px solid #34415a; border-radius: 8px; margin-top: 18px; padding: 16px 8px 8px; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; color: #8be6ce; }
        QPushButton { background: #26374e; border: 1px solid #405674; border-radius: 6px; padding: 9px; }
        QPushButton:hover { background: #344c68; }
        QPushButton:disabled { color: #68768d; }
        QLineEdit, QComboBox, QSpinBox { background: #1c283b; padding: 5px; border: 1px solid #34415a; }
        QLabel { background: transparent; }
    """)
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true", help="Open UI, render a sample, then close automatically")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    configure_theme(app)
    window = Window()
    window.show()
    if args.smoke_test:
        window.overlay.display("플레이어 A · 예시", "Two enemies at B.", "B에 적 두 명 있어.")
        QTimer.singleShot(250, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
