"""Run explicitly with Qt installed: python -m tests.check_ui is not required.
Use: python tests/check_ui.py (with the project installed or PYTHONPATH=.).
"""
import os
from pathlib import Path
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from voice_caption.app import Window, configure_theme

app = QApplication([])
configure_theme(app)
with tempfile.TemporaryDirectory() as temporary:
    os.environ["LOCALAPPDATA"] = temporary
    window = Window()
    window.show()
    app.processEvents()
    window.size.setValue(32)
    window.opacity.setValue(40)
    window.width.setValue(900)
    window.height.setValue(520)
    window.overlay.clear_caption()
    window.overlay.display("플레이어 B · 예시", "I'm watching mid.", "미드는 내가 보고 있어.")
    window.overlay.display("플레이어 A · 예시", "Two enemies at B. Let's go together.", "B에 적 두 명 있어. 같이 가자.")
    assert len(window.overlay.history.items) == 2
    window.error("API 연결 실패 · 테스트")
    window.status.setText("듣는 중")
    assert "API 연결 실패" in window.error_label.text()
    window.lock.setChecked(True)
    assert window.overlay.locked
    window.lock.setChecked(False)
    assert not window.overlay.locked
    assert window.cfg.font_size == 32 and window.cfg.opacity == 40
    assert window.overlay.width() == 900
    window.visible.setChecked(False)
    assert not window.overlay.isVisible()
    window.visible.setChecked(True)
    app.processEvents()
    output = Path(__file__).resolve().parents[1] / "docs"
    assert window.grab().save(str(output / "settings-preview.png"))
    assert window.overlay.grab().save(str(output / "subtitle-preview.png"))
    alpha = window.overlay.grab().toImage().pixelColor(5, 80).alpha()
    assert 95 <= alpha <= 110, f"Background opacity did not apply: {alpha}"
    window.close()
    app.processEvents()
    assert (Path(temporary) / "VoiceCaption" / "settings.json").exists()
    restored = Window()
    assert restored.cfg.font_size == 32
    assert restored.cfg.opacity == 40
    assert restored.overlay.width() == 900
    assert restored.overlay.height() == 520
    if os.name != "nt":
        restored.start_engine()
        assert "Windows" in restored.error_label.text()
        assert restored.engine is None
    restored.close()
    app.processEvents()
print("UI controls, lock state, visibility, screenshot rendering and settings save: PASS")
