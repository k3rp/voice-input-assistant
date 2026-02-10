"""
PyQt6 main window: credential inputs, hotkey configuration,
combined volume meter + silence threshold, and status bar.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from hotkey import HotkeyCombo, HotkeyListener, key_to_str, _MODIFIER_MAP


# Common language codes for the dropdown
LANGUAGES = [
    ("English (US)", "en-US"),
    ("English (UK)", "en-GB"),
    ("Chinese (Mandarin)", "zh"),
    ("Spanish", "es-ES"),
    ("French", "fr-FR"),
    ("German", "de-DE"),
    ("Japanese", "ja-JP"),
    ("Korean", "ko-KR"),
    ("Portuguese (BR)", "pt-BR"),
    ("Hindi", "hi-IN"),
]

# Default hotkey: Ctrl + '
DEFAULT_HOTKEY = HotkeyCombo(modifiers={"ctrl"}, main_key="'")

# Number of capsules in the level meter
NUM_CAPSULES = 16


class CapsuleMeter(QWidget):
    """
    A discrete-capsule volume level meter, modelled after the macOS
    System Preferences "Input level" indicator.

    Draws NUM_CAPSULES rounded rectangles side by side.  Capsules up
    to the current level are "lit" (green); the rest are dark grey.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0          # 0..NUM_CAPSULES
        self._lit_color = QColor("#4caf50")
        self._dim_color = QColor("#3a3a3a")
        self.setMinimumHeight(20)
        self.setMaximumHeight(20)

    def set_level(self, count: int):
        """Set how many capsules should be lit (0..NUM_CAPSULES)."""
        count = max(0, min(NUM_CAPSULES, count))
        if count != self._level:
            self._level = count
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(300, 20)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(Qt.PenStyle.NoPen))

        w = self.width()
        h = self.height()
        gap = 3
        total_gaps = gap * (NUM_CAPSULES - 1)
        capsule_w = max(1, (w - total_gaps) / NUM_CAPSULES)
        radius = min(capsule_w / 2, h / 2, 4)

        for i in range(NUM_CAPSULES):
            x = i * (capsule_w + gap)
            if i < self._level:
                painter.setBrush(self._lit_color)
            else:
                painter.setBrush(self._dim_color)
            painter.drawRoundedRect(int(x), 0, int(capsule_w), h, radius, radius)

        painter.end()


class MainWindow(QMainWindow):
    """Application main window."""

    # Signals emitted to the controller
    recording_requested = pyqtSignal()    # hotkey pressed
    recording_stopped = pyqtSignal()      # hotkey released

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voice Input — GCP Speech-to-Text")
        self.setMinimumWidth(480)

        # Hotkey listener
        self._hotkey_listener = HotkeyListener()
        self._current_combo: HotkeyCombo | None = None
        self._capturing_hotkey = False
        self._capture_modifiers: set[str] = set()

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)

        # --- Credentials group ---
        creds_group = QGroupBox("GCP Credentials")
        creds_layout = QVBoxLayout(creds_group)

        # API Key
        api_key_row = QHBoxLayout()
        api_key_row.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter your Google Cloud API key")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_key_row.addWidget(self.api_key_input)
        self.api_key_toggle = QPushButton("Show")
        self.api_key_toggle.setFixedWidth(60)
        self.api_key_toggle.setCheckable(True)
        self.api_key_toggle.toggled.connect(self._toggle_api_key_visibility)
        api_key_row.addWidget(self.api_key_toggle)
        creds_layout.addLayout(api_key_row)

        # Language
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Language:"))
        self.language_combo = QComboBox()
        for display, code in LANGUAGES:
            self.language_combo.addItem(f"{display} ({code})", code)
        lang_row.addWidget(self.language_combo)
        creds_layout.addLayout(lang_row)

        layout.addWidget(creds_group)

        # --- Hotkey group ---
        hotkey_group = QGroupBox("Hotkey (Push-to-Talk)")
        hotkey_layout = QHBoxLayout(hotkey_group)

        self.hotkey_label = QLabel(str(DEFAULT_HOTKEY))
        self.hotkey_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        hotkey_layout.addWidget(self.hotkey_label)

        self.hotkey_btn = QPushButton("Set Hotkey")
        self.hotkey_btn.clicked.connect(self._start_hotkey_capture)
        hotkey_layout.addWidget(self.hotkey_btn)

        layout.addWidget(hotkey_group)

        # --- Volume group (capsule meter + silence threshold) ---
        volume_group = QGroupBox("Volume")
        volume_layout = QVBoxLayout(volume_group)

        # Capsule input-level meter
        meter_row = QHBoxLayout()
        meter_row.addWidget(QLabel("Input Level"))
        self.capsule_meter = CapsuleMeter()
        meter_row.addWidget(self.capsule_meter)
        self.volume_db_label = QLabel("-∞ dB")
        self.volume_db_label.setFixedWidth(70)
        self.volume_db_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        meter_row.addWidget(self.volume_db_label)
        volume_layout.addLayout(meter_row)

        # Silence threshold slider
        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("Silence Threshold"))
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setMinimum(-60)
        self.threshold_slider.setMaximum(-10)
        self.threshold_slider.setValue(-50)
        self.threshold_slider.setTickInterval(5)
        self.threshold_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.threshold_slider.valueChanged.connect(self._update_threshold_label)
        threshold_row.addWidget(self.threshold_slider)
        self.threshold_value_label = QLabel("-50 dB")
        self.threshold_value_label.setFixedWidth(70)
        self.threshold_value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        threshold_row.addWidget(self.threshold_value_label)
        volume_layout.addLayout(threshold_row)

        layout.addWidget(volume_group)

        # --- Status bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._set_status("Idle")

        # --- Connect hotkey listener signals ---
        self._hotkey_listener.signals.hotkey_pressed.connect(self._on_hotkey_pressed)
        self._hotkey_listener.signals.hotkey_released.connect(self._on_hotkey_released)
        self._hotkey_listener.signals.key_event.connect(self._on_capture_key_event)

        # Apply default hotkey and start the global listener
        self._current_combo = DEFAULT_HOTKEY
        self._hotkey_listener.set_hotkey(DEFAULT_HOTKEY)
        self._hotkey_listener.start()

    # ------------------------------------------------------------------
    # Focus: click anywhere outside a text field to clear focus
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        """Clear focus from text inputs when clicking elsewhere."""
        focused = QApplication.focusWidget()
        if isinstance(focused, QLineEdit):
            focused.clearFocus()
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_api_key(self) -> str:
        return self.api_key_input.text().strip()

    def get_language_code(self) -> str:
        return self.language_combo.currentData()

    def get_threshold_db(self) -> float:
        return float(self.threshold_slider.value())

    # ------------------------------------------------------------------
    # Live volume meter
    # ------------------------------------------------------------------

    @pyqtSlot(float)
    def update_volume(self, rms_db: float):
        """Update the capsule meter with the current dB level."""
        # Map dB range [-80, 0] → capsule count [0, NUM_CAPSULES]
        clamped = max(-80.0, min(0.0, rms_db))
        count = int((clamped + 80.0) / 80.0 * NUM_CAPSULES)
        self.capsule_meter.set_level(count)
        self.volume_db_label.setText(f"{rms_db:.1f} dB")

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str):
        self.status_bar.showMessage(text)

    def set_status_idle(self):
        self._set_status("Idle — press hotkey to record")

    def set_status_recording(self):
        self._set_status("🎙️  Recording…")

    def set_status_transcribing(self):
        self._set_status("⏳  Transcribing…")

    # ------------------------------------------------------------------
    # API key visibility toggle
    # ------------------------------------------------------------------

    @pyqtSlot(bool)
    def _toggle_api_key_visibility(self, checked: bool):
        if checked:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.api_key_toggle.setText("Hide")
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.api_key_toggle.setText("Show")

    # ------------------------------------------------------------------
    # Threshold slider
    # ------------------------------------------------------------------

    @pyqtSlot(int)
    def _update_threshold_label(self, value: int):
        self.threshold_value_label.setText(f"{value} dB")

    # ------------------------------------------------------------------
    # Hotkey capture
    # ------------------------------------------------------------------

    def _start_hotkey_capture(self):
        """Enter hotkey capture mode."""
        self._capturing_hotkey = True
        self._capture_modifiers = set()
        self.hotkey_btn.setText("Press keys…")
        self.hotkey_btn.setEnabled(False)
        self.hotkey_label.setText("Listening…")
        self._hotkey_listener.set_capture_mode(True)

    @pyqtSlot(object, bool)
    def _on_capture_key_event(self, key, is_press: bool):
        """Handle key events during hotkey capture."""
        if not self._capturing_hotkey:
            return

        if is_press:
            if key in _MODIFIER_MAP:
                self._capture_modifiers.add(_MODIFIER_MAP[key])
            else:
                # Non-modifier key pressed — finalize the combo
                main_key = key_to_str(key)
                combo = HotkeyCombo(
                    modifiers=set(self._capture_modifiers),
                    main_key=main_key,
                )
                self._finish_hotkey_capture(combo)

    def _finish_hotkey_capture(self, combo: HotkeyCombo):
        """Finish capturing and apply the new hotkey."""
        self._capturing_hotkey = False
        self._hotkey_listener.set_capture_mode(False)
        self._current_combo = combo
        self._hotkey_listener.set_hotkey(combo)
        self.hotkey_label.setText(str(combo))
        self.hotkey_btn.setText("Set Hotkey")
        self.hotkey_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Hotkey press / release (forwarded as signals)
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_hotkey_pressed(self):
        self.recording_requested.emit()

    @pyqtSlot()
    def _on_hotkey_released(self):
        self.recording_stopped.emit()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._hotkey_listener.stop()
        super().closeEvent(event)
