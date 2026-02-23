"""
Global hotkey listener using pynput.

Tracks modifier state + a main key. When the configured hotkey combo
is pressed, emits a Qt signal to start recording; on release, emits
a signal to stop recording.
"""

from __future__ import annotations

import threading
from typing import Optional, Set, Callable

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

from PyQt6.QtCore import QObject, pyqtSignal


# Mapping of modifier Key objects to a canonical string
_MODIFIER_MAP = {
    Key.ctrl_l: "ctrl",
    Key.ctrl_r: "ctrl",
    Key.shift_l: "shift",
    Key.shift_r: "shift",
    Key.alt_l: "alt",
    Key.alt_r: "alt",
    Key.cmd_l: "cmd",
    Key.cmd_r: "cmd",
}

# Reverse: canonical string -> set of pynput Key objects
_MODIFIER_KEYS: dict[str, set] = {}
for _k, _v in _MODIFIER_MAP.items():
    _MODIFIER_KEYS.setdefault(_v, set()).add(_k)


def key_to_str(key) -> str:
    """Convert a pynput key object to a human-readable string."""
    if key in _MODIFIER_MAP:
        return _MODIFIER_MAP[key]
    if isinstance(key, KeyCode):
        if key.char:
            return key.char.lower()
        if key.vk is not None:
            return f"<{key.vk}>"
    if isinstance(key, Key):
        return key.name
    return str(key)


class HotkeyCombo:
    """Represents a hotkey combination like Ctrl+Shift+R."""

    def __init__(self, modifiers: Optional[Set[str]] = None, main_key: Optional[str] = None):
        self.modifiers: Set[str] = modifiers or set()
        self.main_key: Optional[str] = main_key

    def __str__(self) -> str:
        parts = sorted(self.modifiers) + ([self.main_key.upper()] if self.main_key else [])
        return "+".join(parts)

    def is_valid(self) -> bool:
        return self.main_key is not None


class HotkeySignals(QObject):
    """Qt signals emitted by the hotkey listener."""
    # Primary (auto-paste)
    hotkey_pressed = pyqtSignal()
    hotkey_released = pyqtSignal()
    
    # Secondary (review mode)
    secondary_hotkey_pressed = pyqtSignal()
    secondary_hotkey_released = pyqtSignal()
    
    # Correction
    correction_hotkey_pressed = pyqtSignal()
    
    toggle_settings_requested = pyqtSignal()
    cancel_requested = pyqtSignal()  # Escape pressed: cancel all in-flight work
    key_event = pyqtSignal(object, bool)  # (key, is_press) — used for hotkey capture mode


class HotkeyListener:
    """
    Global hotkey listener that runs pynput in a daemon thread.

    Communicates with the Qt main thread via HotkeySignals.
    """

    def __init__(self):
        self.signals = HotkeySignals()
        self._primary_combo: Optional[HotkeyCombo] = None
        self._secondary_combo: Optional[HotkeyCombo] = None
        self._correction_combo: Optional[HotkeyCombo] = None
        
        self._active_modifiers: Set[str] = set()
        self._primary_down: bool = False
        self._secondary_down: bool = False
        
        self._listener: Optional[keyboard.Listener] = None
        self._capture_mode: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_hotkeys(self, primary: Optional[HotkeyCombo], secondary: Optional[HotkeyCombo], correction: Optional[HotkeyCombo]):
        """Set the hotkey combos to listen for."""
        self._primary_combo = primary
        self._secondary_combo = secondary
        self._correction_combo = correction
        self._primary_down = False
        self._secondary_down = False

    def start(self):
        """Start listening for global key events."""
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        """Stop the listener."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def set_capture_mode(self, enabled: bool):
        """Enable/disable hotkey capture mode (for setting the hotkey)."""
        self._capture_mode = enabled

    # ------------------------------------------------------------------
    # Internal callbacks (run in pynput thread)
    # ------------------------------------------------------------------

    def _matches(self, combo: Optional[HotkeyCombo], key_str: str) -> bool:
        if combo is None or not combo.is_valid():
            return False
        return key_str == combo.main_key and self._active_modifiers == combo.modifiers

    def _on_press(self, key):
        if key == Key.esc:
            self.signals.cancel_requested.emit()
            return

        if self._capture_mode:
            self.signals.key_event.emit(key, True)
            return

        if key in _MODIFIER_MAP:
            self._active_modifiers.add(_MODIFIER_MAP[key])
            return

        key_str = key_to_str(key)
        
        if key_str == "q" and self._active_modifiers == {"ctrl", "shift", "alt"}:
            self.signals.toggle_settings_requested.emit()
            return

        # Check primary
        if self._matches(self._primary_combo, key_str) and not self._primary_down:
            self._primary_down = True
            self.signals.hotkey_pressed.emit()
            return
            
        # Check secondary
        if self._matches(self._secondary_combo, key_str) and not self._secondary_down:
            self._secondary_down = True
            self.signals.secondary_hotkey_pressed.emit()
            return
            
        # Check correction (only fires on press, no hold duration needed)
        if self._matches(self._correction_combo, key_str):
            self.signals.correction_hotkey_pressed.emit()
            return

    def _on_release(self, key):
        if self._capture_mode:
            self.signals.key_event.emit(key, False)
            return

        if key in _MODIFIER_MAP:
            mod_name = _MODIFIER_MAP[key]
            self._active_modifiers.discard(mod_name)
            return

        key_str = key_to_str(key)
        
        if self._primary_down and self._primary_combo and key_str == self._primary_combo.main_key:
            self._primary_down = False
            self.signals.hotkey_released.emit()
            
        if self._secondary_down and self._secondary_combo and key_str == self._secondary_combo.main_key:
            self._secondary_down = False
            self.signals.secondary_hotkey_released.emit()
