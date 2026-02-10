"""
Mouse-following overlay bubbles for recording and transcribing states.

RecordingBubble  — small dark bubble with a pulsing red circle (🎙)
SpinnerBubble    — same bubble with a spinning arc (⏳)

Both follow the mouse cursor while visible.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QColor, QPainter, QPen, QCursor, QBrush, QConicalGradient
from PyQt6.QtWidgets import QWidget


# Shared constants
_SIZE = 44           # bubble diameter
_OFFSET = QPoint(20, 20)  # offset from cursor so the bubble doesn't sit on top


class _BaseBubble(QWidget):
    """
    Base class: frameless, always-on-top, translucent dark bubble
    that follows the mouse cursor.
    """

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool            # keeps it out of the taskbar
            | Qt.WindowType.WindowTransparentForInput  # clicks pass through
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(_SIZE, _SIZE)

        # Timer to follow the cursor
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(30)
        self._follow_timer.timeout.connect(self._follow_cursor)

    def show_at_cursor(self):
        """Show the bubble and start following the cursor."""
        self._follow_cursor()
        self.show()
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
    A small dark bubble with a pulsing red dot — indicates that
    the microphone is actively recording.
    """

    def __init__(self):
        super().__init__()
        self._pulse_phase = 0.0

        # Pulse animation timer
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(40)
        self._pulse_timer.timeout.connect(self._tick_pulse)

    def show_at_cursor(self):
        self._pulse_phase = 0.0
        self._pulse_timer.start()
        super().show_at_cursor()

    def dismiss(self):
        self._pulse_timer.stop()
        super().dismiss()

    def _tick_pulse(self):
        self._pulse_phase += 0.15
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dark semi-transparent background circle
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 30, 30, 200))
        painter.drawEllipse(0, 0, _SIZE, _SIZE)

        # Pulsing red circle in the centre
        pulse = 0.5 + 0.5 * math.sin(self._pulse_phase)  # 0..1
        radius = int(6 + 3 * pulse)
        alpha = int(180 + 75 * pulse)
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

        margin = 10
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        # drawArc expects 1/16th of a degree
        start_angle = self._angle * 16
        span_angle = 270 * 16
        painter.drawArc(rect, start_angle, span_angle)

        painter.end()

