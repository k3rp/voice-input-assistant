# Voice Input

<div align="center">
  <img src="img/demo.gif" width="50%">
</div>

A push-to-talk desktop app that transcribes your speech. Optionally post-processes the transcript with **Gemini**.

Supports macOS and Linux (X11 only; Wayland is not supported).

## Prerequisites

- **Python 3.10+**
- **Google Cloud account** with a billing-enabled project
- A **Google Cloud API key**

## API Key Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Select or create a project with billing enabled
3. Create an API key (**APIs & Services → Credentials → Create Credentials → API key**)
4. Restrict the API key to required APIs (**APIs & Services → Library**):
   - **Cloud Speech-to-Text API**
   - **Generative Language API** *(for Gemini post-processing)*
5. Launch the app, click the 🎙 icon in the menu bar → **Show / Hide Settings**, and paste the key into the **Google Cloud API Key** field

## Installation

```bash
# Clone the repo
git clone https://github.com/yuhao-he/voice-input-assistant.git
cd voice_input

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate   # macOS / Linux

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
source venv/bin/activate
python main.py
```

Press **`Ctrl` + `Shift` + `Alt` + `Q`** anywhere to show or hide the settings menu.

You can also find the settings menu in the menu bar (🎙 icon) on macOS.

