"""
Overlay widgets for the voice input application.

TranscriptOverlay — floating dark box near the cursor that displays the
                    live streaming transcript as it arrives.
RecordingBubble   — small dark bubble with a pulsing red circle (🎙)
SpinnerBubble     — same bubble with a spinning arc (⏳)
"""

from __future__ import annotations

import html
import platform

from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF, QSizeF, pyqtSignal
from PyQt6.QtGui import (
    QShortcut, QKeySequence,
    QColor, QPainter, QPen, QCursor, QBrush, QConicalGradient,
    QFont, QFontMetrics, QTextOption, QTextDocument,
)
from PyQt6.QtWidgets import QWidget, QApplication, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit, QLineEdit, QLabel

_IS_MACOS = platform.system() == "Darwin"

# On macOS, use Cocoa to snapshot and re-activate the previously focused
# app after showing an overlay, so our main window never steals focus.
_ns_workspace = None
if _IS_MACOS:
    try:
        from AppKit import NSWorkspace as _NSWorkspace
        _ns_workspace = _NSWorkspace.sharedWorkspace
    except ImportError:
        pass


def _get_frontmost_app():
    """Return the currently frontmost application (macOS only, else None)."""
    if _ns_workspace is not None:
        return _ns_workspace().frontmostApplication()
    return None


def _reactivate_app(app):
    """Re-activate *app* so our Qt app doesn't stay frontmost (macOS)."""
    if app is not None:
        app.activateWithOptions_(0)


# Shared constants
_SIZE = 32           # bubble diameter
_OFFSET = QPoint(20, 20)  # offset from cursor so the bubble doesn't sit on top


class _BaseBubble(QWidget):
    """
    Base class: frameless, always-on-top, translucent dark bubble
    that follows the mouse cursor.

    Must float above ALL apps without stealing focus or bringing
    the main window forward.  On macOS the Tool window type causes
    application activation on show(); we counter that by immediately
    re-focusing the previously active app via Cocoa.
    """

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool            # keeps it out of the taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # clicks pass through

        # Keep Tool windows visible even when our app is not frontmost.
        if _IS_MACOS:
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)

        self.setFixedSize(_SIZE, _SIZE)

        # Timer to follow the cursor
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(30)
        self._follow_timer.timeout.connect(self._follow_cursor)

    def show_at_cursor(self):
        """Show the bubble and start following the cursor."""
        self._follow_cursor()

        # Snapshot whichever app currently owns focus (e.g. Chrome)
        prev = _get_frontmost_app()
        self.show()
        # Give focus right back so our main window never comes forward
        _reactivate_app(prev)

        self._follow_timer.start()

    def dismiss(self):
        """Hide the bubble and stop the follow timer."""
        self._follow_timer.stop()
        self.hide()

    def _follow_cursor(self):
        pos = QCursor.pos() + _OFFSET
        self.move(pos)


class RecordingBubble(_BaseBubble):
    """
    A small dark bubble with a volume-reactive red dot — indicates that
    the microphone is actively recording.  The red circle grows when
    the user speaks louder and shrinks to a small dot during silence.
    """

    _MIN_RADIUS = 3      # radius when silent
    _MAX_RADIUS = 13     # radius at full volume
    _SMOOTHING_RISE = 0.45   # fast attack
    _SMOOTHING_FALL = 0.12   # slow decay
    # dB range mapped to [0, 1]
    _DB_FLOOR = -60.0
    _DB_CEIL = -10.0

    def __init__(self):
        super().__init__()
        self._volume_t = 0.0       # smoothed volume 0..1
        self._raw_t = 0.0          # latest raw volume 0..1

        # Repaint timer (animation frame rate)
        self._paint_timer = QTimer(self)
        self._paint_timer.setInterval(30)
        self._paint_timer.timeout.connect(self._tick)

    def show_at_cursor(self):
        self._volume_t = 0.0
        self._raw_t = 0.0
        self._paint_timer.start()
        super().show_at_cursor()

    def dismiss(self):
        self._paint_timer.stop()
        super().dismiss()

    def set_volume(self, rms_db: float):
        """Set the current volume level (called from Qt main thread)."""
        clamped = max(self._DB_FLOOR, min(self._DB_CEIL, rms_db))
        self._raw_t = (clamped - self._DB_FLOOR) / (self._DB_CEIL - self._DB_FLOOR)

    def _tick(self):
        # Smooth towards the raw value
        alpha = self._SMOOTHING_RISE if self._raw_t >= self._volume_t else self._SMOOTHING_FALL
        self._volume_t += alpha * (self._raw_t - self._volume_t)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dark semi-transparent background circle
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 30, 30, 200))
        painter.drawEllipse(0, 0, _SIZE, _SIZE)

        # Volume-reactive red circle in the centre
        t = self._volume_t
        radius = int(self._MIN_RADIUS + (self._MAX_RADIUS - self._MIN_RADIUS) * t)
        alpha = int(160 + 95 * t)
        cx, cy = _SIZE // 2, _SIZE // 2
        painter.setBrush(QColor(220, 50, 50, alpha))
        painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        painter.end()


class SpinnerBubble(_BaseBubble):
    """
    A small dark bubble with a spinning arc — indicates that
    transcription is in progress.
    """

    def __init__(self):
        super().__init__()
        self._angle = 0

        # Spin animation timer
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(30)
        self._spin_timer.timeout.connect(self._tick_spin)

    def show_at_cursor(self):
        self._angle = 0
        self._spin_timer.start()
        super().show_at_cursor()

    def dismiss(self):
        self._spin_timer.stop()
        super().dismiss()

    def _tick_spin(self):
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dark semi-transparent background circle
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 30, 30, 200))
        painter.drawEllipse(0, 0, _SIZE, _SIZE)

        # Spinning arc
        pen = QPen(QColor(200, 200, 200, 230), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        margin = 7
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        # drawArc expects 1/16th of a degree
        start_angle = self._angle * 16
        span_angle = 270 * 16
        painter.drawArc(rect, start_angle, span_angle)

        painter.end()


# -----------------------------------------------------------------------
# Transcript overlay — shows live streaming transcript near the cursor
# -----------------------------------------------------------------------

_OVERLAY_PADDING = 12
_OVERLAY_MAX_WIDTH = 420
_OVERLAY_CORNER_RADIUS = 10
_OVERLAY_OFFSET = QPoint(24, 24)   # offset from cursor

# Braille spinner frames cycled by the spin timer
_SPIN_CHARS = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷']


class TranscriptOverlay(QWidget):
    """
    A floating dark rounded-rect box that displays the live transcript,
    supporting multiple concurrent segments:

    - **active** segment  — the one currently being transcribed (bright white).
    - **processing** segment — sent to Gemini, awaiting result (semi-white +
      spinning braille char appended inline).

    Public API
    ----------
    show_at_cursor()
        Append a new empty *active* segment; show the widget if hidden.
    set_text(text)
        Update the last *active* segment's text.
    freeze_active_segment() -> int
        Mark the last active segment as *processing* (semi-white + spinner).
        Returns the segment's unique id so the caller can later call
        ``complete_segment(seg_id)``.
    complete_segment(seg_id)
        Remove the segment with *seg_id* from the list.  Auto-hides when
        the list becomes empty.
    dismiss()
        Unconditionally clear all segments and hide.
    """

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        if _IS_MACOS:
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)

        # Segment list — each entry: {"id": int, "text": str, "state": str}
        # state is "active" or "processing"
        self._segments: list[dict] = []
        self._next_id: int = 0

        # Shared spinner animation state
        self._spin_frame: int = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(80)
        self._spin_timer.timeout.connect(self._tick_spin)

        font_name = "SF Pro Text" if _IS_MACOS else "Segoe UI"
        self._font = QFont(font_name, 14)
        self._font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self._metrics = QFontMetrics(self._font)

        # Cursor-follow timer
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(30)
        self._follow_timer.timeout.connect(self._follow_cursor)

        self._update_size()

    # -- public API -------------------------------------------------------

    def show_error_at_cursor(self, msg: str, duration_ms: int = 4000):
        """Show a transient error message near the cursor in light red.

        The message auto-dismisses after *duration_ms* milliseconds.
        """
        seg_id = self._next_id
        self._segments.append({"id": seg_id, "text": msg, "state": "error"})
        self._next_id += 1

        if not self.isVisible():
            self._follow_cursor()
            prev = _get_frontmost_app()
            self.show()
            _reactivate_app(prev)
            self._follow_timer.start()

        self._update_size()
        self.update()

        # Auto-dismiss this error segment after the given delay.
        QTimer.singleShot(duration_ms, lambda: self.complete_segment(seg_id))

    def show_at_cursor(self):
        """Append a new active segment; show + start following the cursor."""
        self._segments.append({"id": self._next_id, "text": "", "state": "active"})
        self._next_id += 1

        if not self.isVisible():
            self._follow_cursor()
            prev = _get_frontmost_app()
            self.show()
            _reactivate_app(prev)
            self._follow_timer.start()

        self._update_size()
        self.update()

    def set_text(self, text: str):
        """Update the last active segment's text (called with live interim transcript)."""
        if self._segments and self._segments[-1]["state"] == "active":
            self._segments[-1]["text"] = text
        self._update_size()
        self.update()

    def freeze_active_segment(self) -> int:
        """
        Mark the last active segment as *processing* (semi-white + spinner).
        Starts the spinner animation if not already running.
        Returns the segment id.
        """
        seg_id = -1
        for seg in reversed(self._segments):
            if seg["state"] == "active":
                seg["state"] = "processing"
                seg_id = seg["id"]
                break

        if not self._spin_timer.isActive():
            self._spin_timer.start()

        self._update_size()
        self.update()
        return seg_id

    def complete_segment(self, seg_id: int):
        """
        Remove the segment with *seg_id* from the display.
        Auto-hides (and stops timers) when no segments remain.
        """
        self._segments = [s for s in self._segments if s["id"] != seg_id]

        # Stop spinner if nothing left to spin
        has_processing = any(s["state"] == "processing" for s in self._segments)
        if not has_processing:
            self._spin_timer.stop()

        if not self._segments:
            self._hide_all()
        else:
            self._update_size()
            self.update()

    def dismiss(self):
        """Unconditionally clear all segments and hide."""
        self._segments.clear()
        self._hide_all()

    # -- internals --------------------------------------------------------

    def _hide_all(self):
        self._spin_timer.stop()
        self._follow_timer.stop()
        self.hide()
        self._update_size()

    def _tick_spin(self):
        self._spin_frame = (self._spin_frame + 1) % len(_SPIN_CHARS)
        self.update()

    def _follow_cursor(self):
        pos = QCursor.pos() + _OVERLAY_OFFSET

        screen = QApplication.screenAt(QCursor.pos())
        if screen is not None:
            geo = screen.availableGeometry()
            if pos.x() + self.width() > geo.right():
                pos.setX(geo.right() - self.width())
            if pos.y() + self.height() > geo.bottom():
                pos.setY(QCursor.pos().y() - _OVERLAY_OFFSET.y() - self.height())
            if pos.x() < geo.left():
                pos.setX(geo.left())
            if pos.y() < geo.top():
                pos.setY(geo.top())

        self.move(pos)

    def _build_html(self) -> str:
        """
        Build an HTML string representing all segments.

        - Processing segments: semi-white text + spinner char.
        - Active segment: bright white text (or placeholder if empty).
        """
        spinner = _SPIN_CHARS[self._spin_frame]
        parts: list[str] = []

        for seg in self._segments:
            escaped = html.escape(seg["text"])
            if seg["state"] == "error":
                # Light red — signals a configuration / API error
                parts.append(
                    f'<span style="color:rgba(255,110,110,240);">'
                    f'{escaped}'
                    f'</span>'
                )
            elif seg["state"] == "processing":
                # Semi-white + spinner appended inline
                text_part = escaped if escaped else "…"
                parts.append(
                    f'<span style="color:rgba(255,255,255,130);">'
                    f'{text_part}&nbsp;{spinner}'
                    f'</span>'
                )
            else:
                # Active — bright white
                if escaped:
                    parts.append(
                        f'<span style="color:rgba(255,255,255,240);">'
                        f'{escaped}'
                        f'</span>'
                    )
                else:
                    # Placeholder when nothing transcribed yet
                    parts.append(
                        f'<span style="color:rgba(180,180,180,160);">Listening…</span>'
                    )

        # Join segments with a visible separator space
        return '<span style="color:rgba(255,255,255,80);">&nbsp; </span>'.join(parts)

    def _make_doc(self, max_text_w: float) -> QTextDocument:
        """Create a QTextDocument sized to *max_text_w* with current HTML."""
        doc = QTextDocument()
        doc.setDefaultFont(self._font)
        doc.setTextWidth(max_text_w)
        doc.setHtml(self._build_html())
        return doc

    def _update_size(self):
        """Recalculate widget size to fit the current segments."""
        p = _OVERLAY_PADDING
        if not self._segments:
            self.setFixedSize(p * 2 + 60, p * 2 + self._metrics.height())
            return

        max_text_w = _OVERLAY_MAX_WIDTH - 2 * p
        doc = self._make_doc(max_text_w)
        doc_size = doc.size()
        w = min(int(doc_size.width()) + 2 * p + 4, _OVERLAY_MAX_WIDTH)
        h = int(doc_size.height()) + 2 * p + 4
        self.setFixedSize(max(w, 80), max(h, p * 2 + self._metrics.height()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dark rounded-rect background
        painter.setBrush(QColor(30, 30, 30, 240))
        painter.setPen(QPen(QColor(80, 80, 80, 150), 1))
        
        rect = self.rect()
        rect.adjust(1, 1, -2, -2) # thick soft borders
        painter.drawRoundedRect(rect, 12, 12)

        p = _OVERLAY_PADDING
        max_text_w = self.width() - 2 * p

        if self._segments:
            doc = self._make_doc(max_text_w)
            painter.translate(p, p)
            doc.drawContents(painter)
        else:
            painter.setFont(self._font)
            painter.setPen(QColor(180, 180, 180, 160))
            text_rect = QRectF(p, p, max_text_w, self.height() - 2 * p)
            option = QTextOption()
            option.setWrapMode(QTextOption.WrapMode.WordWrap)
        painter.end()


# -----------------------------------------------------------------------
# Review Window — editable transcript with Insert, Copy, Close buttons
# -----------------------------------------------------------------------

class ReviewWindow(QWidget):
    """
    A floating window shown after a Secondary Hotkey transcription is complete.
    Allows the user to manually edit the text before inserting, copying, or discarding.
    """

    # Signals for the controller
    insert_requested = pyqtSignal(str)   # text
    copy_requested = pyqtSignal(str)     # text
    closed = pyqtSignal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if _IS_MACOS:
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)

        # Build UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        font_name = "SF Pro Text" if _IS_MACOS else "Segoe UI"
        font = QFont(font_name, 14)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setFont(font)
        # Match main UI styling
        self.setStyleSheet("""
            * {
                color: #e0e0e0;
            }
            QPushButton {
                background-color: #333333;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 6px 16px;
                color: #ffffff;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #404040;
                border-color: #555555;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
            }
            QPlainTextEdit {
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #444;
            }
            QPlainTextEdit:focus {
                border: 1px solid #666;
            }
        """)
        layout.addWidget(self.text_edit)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_insert = QPushButton("✨ Insert")
        self.btn_insert.setToolTip("Auto-paste text into the last app and close (F3)")
        
        self.btn_copy = QPushButton("📋 Copy")
        self.btn_copy.setToolTip("Copy text to clipboard and close (Ctrl+C)")
        
        self.btn_close = QPushButton("❌ Cancel")
        self.btn_close.setToolTip("Discard transcript and close (Esc)")



        btn_layout.addWidget(self.btn_insert)
        btn_layout.addWidget(self.btn_copy)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        # Connections
        self.btn_insert.clicked.connect(self._on_insert)
        self.btn_copy.clicked.connect(self._on_copy)
        self.btn_close.clicked.connect(self._on_close)
        
        # Robust hotkeys that intercept even when QPlainTextEdit is focused


        self.setFixedSize(450, 160)
        # Install an event filter to intercept keystrokes inside the text editor
        self.text_edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent, Qt
        if obj is self.text_edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            
            if key == Qt.Key.Key_Escape:
                self._on_close()
                return True
                
            elif key == Qt.Key.Key_C and (modifiers & Qt.KeyboardModifier.ControlModifier or modifiers & Qt.KeyboardModifier.MetaModifier):
                # The user hit Ctrl+C! We powerfully copy the selection (or whole text) and close.
                self._on_copy()
                return True
                

                
            elif key == Qt.Key.Key_Return and (modifiers & Qt.KeyboardModifier.ControlModifier or modifiers & Qt.KeyboardModifier.MetaModifier):
                self._on_insert()
                return True
                
        return super().eventFilter(obj, event)

    def show_with_text(self, text: str):
        """Populate the text editor and show the window."""
        self.text_edit.setPlainText(text)
        
        # Position offset directly to the bottom right of the cursor (matching the transcription bubble)
        pos = QCursor.pos()
        target_pos = pos + QPoint(24, 24)
        
        screen = QApplication.screenAt(pos)
        if screen:
            geom = screen.availableGeometry()
            # Clamp the window to the screen bounds to prevent it from going off-edge
            
            # If the window would overflow the right side, flip it to the left side of the cursor
            if target_pos.x() + self.width() > geom.right() - 20:
                target_pos.setX(pos.x() - self.width() - 24)
                
            # If the window would overflow the bottom side, flip it above the cursor
            if target_pos.y() + self.height() > geom.bottom() - 20:
                target_pos.setY(pos.y() - self.height() - 24)
                
            # Final hard clamp in case the cursor is in a weird absolute corner and the flip still overflows
            target_pos.setX(max(geom.left() + 20, min(target_pos.x(), geom.right() - self.width() - 20)))
            target_pos.setY(max(geom.top() + 20, min(target_pos.y(), geom.bottom() - self.height() - 20)))
        
        self.move(target_pos)
            
        prev = _get_frontmost_app()
        self.show()
        self.raise_()
        self.activateWindow()
        self.text_edit.setFocus()
        
        # Don't reactivate the old app here, because the user actually needs
        # to interact with this window to click the buttons/edit text!

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # We fill it with a frosted glass-like dark bubble
        painter.setBrush(QColor(30, 30, 30, 240))
        painter.setPen(QPen(QColor(80, 80, 80, 150), 1))
        
        rect = self.rect()
        rect.adjust(1, 1, -2, -2) # thick soft borders
        painter.drawRoundedRect(rect, 12, 12)
        painter.end()

    def _on_insert(self):
        text = self.text_edit.toPlainText().strip()
        self.hide()
        self.insert_requested.emit(text)

    def _on_copy(self):
        text = self.text_edit.textCursor().selectedText().strip()
        if not text:
            text = self.text_edit.toPlainText().strip()
        self.hide()
        self.copy_requested.emit(text)


    def keyPressEvent(self, event):
        from PyQt6.QtCore import Qt
        # Intercept hotkeys inside the UI
        modifiers = event.modifiers()
        key = event.key()
        
        if key == Qt.Key.Key_Escape:
            self._on_close()
        elif key == Qt.Key.Key_C and (modifiers & Qt.KeyboardModifier.ControlModifier or modifiers & Qt.KeyboardModifier.MetaModifier):
            self._on_copy()
        # F3 and Shift+F3 are handled gracefully by the global pynput hotkey listener triggering main.py
        else:
            super().keyPressEvent(event)

    def _on_close(self):
        self.hide()
        self.closed.emit()

class CorrectionWindow(QWidget):
    """A floating window for adding in-line word correction rules."""
    correction_added = pyqtSignal(str, str)
    closed = pyqtSignal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if _IS_MACOS:
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        font_name = "SF Pro Text" if _IS_MACOS else "Segoe UI"
        font = QFont(font_name, 14)

        self.label = QLabel()
        self.label.setFont(font)
        
        self.input_edit = QLineEdit()
        self.input_edit.setFont(font)
        self.input_edit.returnPressed.connect(self._on_save)

        self.setStyleSheet("""
            * {
                color: #e0e0e0;
            }
            QPushButton {
                background-color: #333333;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 6px 16px;
                color: #ffffff;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #404040;
                border-color: #555555;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
            }
            QLineEdit {
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #444;
            }
            QLineEdit:focus {
                border: 1px solid #666;
            }
        """)

        layout.addWidget(self.label)
        layout.addWidget(self.input_edit)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_save = QPushButton("✨ Add Rule")
        self.btn_save.setToolTip("Save correction rule and close (Enter)")
        
        self.btn_close = QPushButton("❌ Cancel")
        self.btn_close.setToolTip("Discard and close (Esc)")

        btn_layout.addWidget(self.btn_save)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        self.btn_save.clicked.connect(self._on_save)
        self.btn_close.clicked.connect(self._on_close)

        self.setFixedSize(420, 130)
        self._original_text = ""

    def show_with_text(self, text: str):
        self._original_text = text.strip()
        self.label.setText(f"Whenever GCP hears: <b>\"{self._original_text}\"</b>")
        self.input_edit.setText(self._original_text)
        self.input_edit.selectAll()
        
        pos = QCursor.pos()
        target_pos = pos + QPoint(24, 24)
        screen = QApplication.screenAt(pos)
        if screen:
            geom = screen.availableGeometry()
            if target_pos.x() + self.width() > geom.right() - 20:
                target_pos.setX(pos.x() - self.width() - 24)
            if target_pos.y() + self.height() > geom.bottom() - 20:
                target_pos.setY(pos.y() - self.height() - 24)
                
        self.move(target_pos)
        prev = _get_frontmost_app()
        self.show()
        self.raise_()
        self.activateWindow()
        _reactivate_app(prev)
        self.input_edit.setFocus()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(30, 30, 30, 240))
        painter.setPen(QPen(QColor(80, 80, 80, 150), 1))
        rect = self.rect()
        rect.adjust(1, 1, -2, -2)
        painter.drawRoundedRect(rect, 12, 12)
        painter.end()

    def _on_save(self):
        new_text = self.input_edit.text().strip()
        if new_text and self._original_text:
            self.correction_added.emit(self._original_text, new_text)
        self._on_close()

    def _on_close(self):
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, event):
        from PyQt6.QtCore import Qt
        if event.key() == Qt.Key.Key_Escape:
            self._on_close()
        else:
            super().keyPressEvent(event)
