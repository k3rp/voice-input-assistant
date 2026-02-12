"""
GCP Speech-to-Text **v2** caller using the ``google-cloud-speech`` library.

Authentication uses Application Default Credentials (ADC).
Run ``gcloud auth application-default login`` before starting the app.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech

# Lazy-initialised client (gRPC channel reuse across calls)
_client: Optional[SpeechClient] = None
_project_id: Optional[str] = None


def _get_client() -> tuple[SpeechClient, str]:
    """Return a (SpeechClient, project_id) pair, creating them on first call."""
    global _client, _project_id
    if _client is None:
        import google.auth

        credentials, project = google.auth.default()
        if not project:
            raise RuntimeError(
                "Could not determine GCP project. "
                "Set it with:  gcloud config set project YOUR_PROJECT_ID"
            )
        _client = SpeechClient(credentials=credentials)
        _project_id = project
    return _client, _project_id


def transcribe(
    audio: np.ndarray,
    language_code: str = "en-US",
    sample_rate: int = 16000,
) -> Optional[str]:
    """
    Send audio to GCP Speech-to-Text v2 and return the transcript.

    Parameters
    ----------
    audio : np.ndarray
        1-D int16 PCM audio samples.
    language_code : str
        BCP-47 language code, e.g. "en-US".
    sample_rate : int
        Sample rate of the audio.

    Returns
    -------
    str or None
        The transcribed text, or *None* on failure / empty result.
    """
    if audio is None or len(audio) == 0:
        return None

    audio_bytes = audio.astype(np.int16).tobytes()

    try:
        client, project_id = _get_client()
    except Exception as exc:
        print(f"[Transcriber] Failed to initialise client: {exc}")
        return None

    config = cloud_speech.RecognitionConfig(
        explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
            encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            audio_channel_count=1,
        ),
        language_codes=[language_code],
        model="short",
        features=cloud_speech.RecognitionFeatures(
            enable_automatic_punctuation=True,
        ),
    )

    request = cloud_speech.RecognizeRequest(
        recognizer=f"projects/{project_id}/locations/global/recognizers/_",
        config=config,
        content=audio_bytes,
    )

    try:
        response = client.recognize(request=request)
    except Exception as exc:
        print(f"[Transcriber] API call failed: {exc}")
        return None

    transcripts = []
    for result in response.results:
        if result.alternatives:
            transcripts.append(result.alternatives[0].transcript)

    full_text = " ".join(transcripts).strip()
    return full_text if full_text else None
