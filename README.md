# Voice Input

A push-to-talk desktop app that records your voice, sends it to **Google Cloud Speech-to-Text v2**, and automatically pastes the transcription into whatever app has focus.

## Features

- **Push-to-talk** with a configurable global hotkey (default: `Ctrl + '`)
- **Auto-paste** — transcribed text is pasted directly into the focused input field
- **Live volume meter** with adjustable silence threshold
- **Mouse-following overlays** — a red dot while recording, a spinner while transcribing
- **Multiple languages** — English, Chinese, Spanish, French, German, Japanese, Korean, Portuguese, Hindi
- **Cross-platform** — works on macOS, Windows, and Linux

## Prerequisites

- **Python 3.10+**
- **Google Cloud account** with the Speech-to-Text API enabled
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

1. The app window will open with a language selector, hotkey config, and volume meter.
2. Hold the hotkey (`Ctrl + '` by default) to record.
3. Release the hotkey — the audio is trimmed, sent to Google Cloud, and the transcription is pasted into the currently focused app.

## Project Structure

| File | Description |
|---|---|
| `main.py` | Entry point — wires together recording, transcription, and UI |
| `ui.py` | PyQt6 main window (settings, hotkey config, volume meter) |
| `transcriber.py` | GCP Speech-to-Text v2 client (uses Application Default Credentials) |
| `recorder.py` | Audio recording and silence trimming |
| `overlay.py` | Mouse-following overlay bubbles (recording dot, spinner) |
| `hotkey.py` | Global hotkey listener |
| `sounds.py` | Start/stop audio chirps |

