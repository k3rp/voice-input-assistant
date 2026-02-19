"""
Voice Input Application — Entry Point

Wires together:
  hotkey press  → sound chirp + transcript overlay + start streaming
  hotkey release → sound chirp + finish streaming → post-process → auto-paste

While the hotkey is held, audio is streamed to the Speech-to-Text API
and the live transcript is displayed in a floating overlay near the cursor.

On transcription, the text is pasted into the currently focused input
via a clipboard-swap technique (save → set → paste keystroke → restore).
"""

from __future__ import annotations

import platform
import sys
import threading

from PyQt6.QtCore import QMimeData, QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from pynput.keyboard import Controller as KbController, Key

# Determine the correct modifier for paste (Cmd on macOS, Ctrl elsewhere)
_PASTE_MODIFIER = Key.cmd if platform.system() == "Darwin" else Key.ctrl

from recorder import AudioRecorder
from transcriber import transcribe_streaming
from postprocess import postprocess
from sounds import play_start, play_stop
from overlay import TranscriptOverlay
from ui import MainWindow


class AppController(QObject):
    """
    Coordinates recording, trimming, and transcription.
    Runs the transcription pipeline in a background thread to avoid
    blocking the UI.
    """

    transcription_done = pyqtSignal(str, int)   # emitted when result is ready (text, seg_id)
    transcription_failed = pyqtSignal(str, int) # emitted on error or silence (msg, seg_id)
    interim_transcript = pyqtSignal(str)        # emitted with live transcript text

    def __init__(self, window: MainWindow):
        super().__init__()
        self.window = window
        self.recorder = AudioRecorder()

        self.__kb = None  # created lazily to avoid Quartz/Qt startup race

        # Transcript overlay (replaces old recording / spinner bubbles)
        self._transcript_overlay = TranscriptOverlay()

        # Streaming state — per-job containers, keyed by segment id
        # Each entry: {"thread": Thread, "result_box": [str|None]}
        self._active_job: dict | None = None

        # Connect window signals
        self.window.recording_requested.connect(self.on_start_recording)
        self.window.recording_stopped.connect(self.on_stop_recording)

        # Connect result signals back to UI updates (both carry seg_id as 2nd arg)
        self.transcription_done.connect(self._on_transcription_done)
        self.transcription_failed.connect(self._on_transcription_failed)

        # Live transcript updates → overlay
        self.interim_transcript.connect(self._transcript_overlay.set_text)

    @property
    def _kb(self):
        """Lazily create the pynput keyboard controller on first use."""
        if self.__kb is None:
            self.__kb = KbController()
        return self.__kb

    def _on_interim_callback(self, text: str):
        """Called from the streaming thread — emit a Qt signal to cross threads safely."""
        self.interim_transcript.emit(text)

    @pyqtSlot()
    def on_start_recording(self):
        play_start()
        # show_at_cursor() appends a new active segment (or shows overlay if hidden)
        self._transcript_overlay.show_at_cursor()
        self.window.set_status_recording()
        self.recorder.start()

        # Kick off streaming transcription in a background thread.
        # Each job uses its own result_box so concurrent jobs don't clash.
        language = self.window.get_language_code()
        result_box: list[str | None] = [None]
        thread = threading.Thread(
            target=self._streaming_worker,
            args=(self.recorder.audio_queue, language, result_box),
            daemon=True,
        )
        self._active_job = {"thread": thread, "result_box": result_box}
        thread.start()

    @pyqtSlot()
    def on_stop_recording(self):
        # Stopping the recorder pushes a None sentinel into the audio
        # queue, which causes the streaming generator to end gracefully.
        self.recorder.stop()

        play_stop()

        # Freeze the current active segment: it turns semi-white with a
        # spinner while Gemini post-processes it.
        seg_id = self._transcript_overlay.freeze_active_segment()

        # Capture the current job's thread and result_box before a new
        # recording could overwrite self._active_job.
        job = self._active_job
        thread_ref = job["thread"] if job else None
        result_box = job["result_box"] if job else [None]

        self.window.set_status_transcribing()

        # Wait for the streaming thread to finish, then post-process.
        prompt = self.window.get_postproc_prompt()
        threading.Thread(
            target=self._wait_for_streaming,
            args=(thread_ref, result_box, prompt, seg_id),
            daemon=True,
        ).start()

    def _streaming_worker(self, audio_queue, language, result_box: list):
        """
        Runs in a background thread.  Streams audio to the API and
        stores the final transcript in *result_box[0]*.
        """
        text = transcribe_streaming(
            audio_queue=audio_queue,
            language_code=language,
            on_interim=self._on_interim_callback,
        )
        result_box[0] = text

    def _wait_for_streaming(
        self,
        thread: threading.Thread | None,
        result_box: list,
        prompt: str,
        seg_id: int,
    ):
        """
        Runs in a background thread.  Waits for *thread* to finish,
        applies post-processing, and emits the result paired with *seg_id*.
        """
        if thread is not None:
            thread.join()

        text = result_box[0]

        if not text:
            self.transcription_failed.emit("No transcription returned.", seg_id)
            return

        # Post-process via Gemini if a prompt is configured
        if prompt:
            print(f"[Postprocess] Sending to Gemini… (Transcription: {text})")
            text = postprocess(text, prompt)
            print(f"[Postprocess] Result: {text}")

        self.transcription_done.emit(text, seg_id)

    # ------------------------------------------------------------------
    # Clipboard-swap auto-paste
    # ------------------------------------------------------------------

    @pyqtSlot(str, int)
    def _on_transcription_done(self, text: str, seg_id: int):
        print(f"\n>>> {text}\n")

        # Remove this segment from the overlay; auto-hides if nothing remains.
        self._transcript_overlay.complete_segment(seg_id)

        clipboard = QApplication.clipboard()

        # 1. Save current clipboard contents
        saved_mime = QMimeData()
        source_mime = clipboard.mimeData()
        if source_mime is not None:
            for fmt in source_mime.formats():
                saved_mime.setData(fmt, source_mime.data(fmt))

        # 2. Put transcription text into clipboard
        clipboard.setText(text)

        # 3. Schedule the paste keystroke via QTimer so the event loop
        #    can process the clipboard ownership change first.
        #    (Using time.sleep here would block the event loop and
        #    prevent Qt from serving clipboard data to the target app.)
        def _do_paste():
            self._kb.press(_PASTE_MODIFIER)
            self._kb.press("v")
            self._kb.release("v")
            self._kb.release(_PASTE_MODIFIER)

        QTimer.singleShot(80, _do_paste)

        # 4. Restore original clipboard after paste has had time to complete
        def _restore():
            clipboard.setMimeData(saved_mime)

        QTimer.singleShot(350, _restore)

        # Only return to idle once the overlay has nothing left to show
        if not self._transcript_overlay.isVisible():
            self.window.set_status_idle()

    @pyqtSlot(str, int)
    def _on_transcription_failed(self, msg: str, seg_id: int):
        print(f"[Info] {msg}")
        self._transcript_overlay.complete_segment(seg_id)
        if not self._transcript_overlay.isVisible():
            self.window.set_status_idle()


_SETUP_BANNER = """\
╔══════════════════════════════════════════════════════════════════╗
║  Voice Input — GCP Speech-to-Text v2                           ║
║                                                                ║
║  Setup (run once in your terminal):                            ║
║                                                                ║
║    1. Install the gcloud CLI                                   ║
║         https://cloud.google.com/sdk/docs/install              ║
║                                                                ║
║    2. Log in with Application Default Credentials              ║
║         gcloud auth application-default login                  ║
║                                                                ║
║    3. Set your default project                                 ║
║         gcloud config set project YOUR_PROJECT_ID              ║
║                                                                ║
║    4. Enable the Speech-to-Text API                            ║
║         gcloud services enable speech.googleapis.com           ║
╚══════════════════════════════════════════════════════════════════╝
"""


def main():
    print(_SETUP_BANNER)

    app = QApplication(sys.argv)
    app.setOrganizationName("VoiceInput")
    app.setApplicationName("Voice Input")

    window = MainWindow()
    controller = AppController(window)  # noqa: F841 — prevent GC

    window.show()
    window.set_status_idle()

    app.exec()


if __name__ == "__main__":
    main()
