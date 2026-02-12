"""Clear all saved Voice Input settings (QSettings)."""

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
app.setOrganizationName("VoiceInput")
app.setApplicationName("Voice Input")

settings = QSettings()
settings.clear()
settings.sync()

print("Settings cleared.")

