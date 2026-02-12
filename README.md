# Voice Input

A push-to-talk desktop app that records your voice, sends it to **Google Cloud Speech-to-Text**, and automatically pastes the transcription into whatever app has focus. Optionally post-processes the transcript with **Gemini** before pasting.

Supports macOS and Linux (X11 only; Wayland is not supported).

## Prerequisites

- **Python 3.10+**
- **Google Cloud account** with the Speech-to-Text and Vertex AI APIs enabled
- **gcloud CLI** — [Install guide](https://cloud.google.com/sdk/docs/install)

## GCP Setup

Run these commands once in your terminal:

```bash
# 1. Authenticate with Application Default Credentials
gcloud auth application-default login

# 2. Set your default GCP project
gcloud config set project YOUR_PROJECT_ID

# 3. Enable the Speech-to-Text API
gcloud services enable speech.googleapis.com

# 4. Enable the Vertex AI API (for Gemini post-processing)
gcloud services enable aiplatform.googleapis.com
```

## Installation

```bash
# Clone the repo
git clone <repo-url>
cd voice_input

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate   # macOS / Linux
# venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
source venv/bin/activate
python main.py
```

1. The app window will open with a language selector, hotkey config, volume meter, and post-transcription editing prompt.
2. Hold the hotkey to record.
3. Release the hotkey — the audio is trimmed, sent to Google Cloud, optionally post-processed by Gemini, and the result is pasted into the currently focused app.

### Post Transcription Editing

Enter a prompt in the "Post Transcription Editing" box. Each transcript is sent to **Gemini** along with your prompt before being pasted. Leave the box empty to disable post-processing.

