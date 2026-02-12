"""
Post-process transcribed text via Gemini on Vertex AI.

Uses Application Default Credentials (the same ``gcloud auth
application-default login`` that Speech-to-Text uses).
"""

from __future__ import annotations

from typing import Optional

from google import genai
import google.auth

_MODEL = "gemini-2.0-flash"

# Lazy-initialised client
_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    """Return a Vertex AI–backed GenAI client, creating it on first call."""
    global _client
    if _client is None:
        _, project = google.auth.default()
        if not project:
            raise RuntimeError(
                "Could not determine GCP project. "
                "Set it with:  gcloud config set project YOUR_PROJECT_ID"
            )
        _client = genai.Client(
            vertexai=True,
            project=project,
            location="us-central1",
        )
    return _client


def postprocess(transcript: str, prompt: str) -> str:
    """
    Send *transcript* + *prompt* to Gemini and return the model's response.

    Parameters
    ----------
    transcript : str
        The raw transcription from Speech-to-Text.
    prompt : str
        User-defined instruction (e.g. "Fix grammar and punctuation").

    Returns
    -------
    str
        The post-processed text, or the original transcript on failure.
    """
    prompt = prompt.strip() if prompt else ""
    if not prompt or not transcript:
        return transcript

    full_prompt = (
        f"{prompt}\n\n"
        f"Transcript:\n{transcript}\n\n"
        f"Respond ONLY with the processed text, nothing else."
    )

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=_MODEL,
            contents=full_prompt,
        )
        result = response.text.strip()
        return result if result else transcript
    except Exception as exc:
        print(f"[Postprocess] Gemini call failed: {exc}")
        return transcript
