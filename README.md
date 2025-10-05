# Real-Time Video Translation & Dubbing (Single User)

A proof-of-concept web app that captures live video+audio, performs speech-to-text (ASR), translates it, synthesizes dubbed audio (TTS), and plays it back alongside the live video.

- Frontend: React + Vite, WebRTC `getUserMedia`, `MediaRecorder`
- Backend: FastAPI
- ASR: Vosk (offline, free model download)
- Translation: LibreTranslate (public instance by default)
- TTS: gTTS (Google Text-to-Speech)

This is an interview prototype, not a production system.

## Repo Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models/
│   │   │   └── schemas.py
│   │   ├── services/
│   │   │   ├── asr_vosk.py
│   │   │   ├── translate_libre.py
│   │   │   └── tts_gtts.py
│   │   └── utils/
│   │       └── audio.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── vite.config.js
│   ├── .env.example
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api.js
│       └── styles.css
└── README.md
```

## Prerequisites

- Python 3.10+
- Node 18+
- FFmpeg installed and on PATH (for audio transcoding)
  - Windows: download from https://www.gyan.dev/ffmpeg/builds/, add `bin/` to PATH
- Vosk model (small) for source language (default: English)
  - Download e.g. `vosk-model-small-en-us-0.15` from https://alphacephei.com/vosk/models
  - Unzip somewhere and set `VOSK_MODEL_PATH` in `backend/.env`

## Configure Environment

1) Backend

Copy and edit environment file:

```
cp backend/.env.example backend/.env
```

`backend/.env`:

```
# Path to local Vosk model directory
VOSK_MODEL_PATH=e:/models/vosk-model-small-en-us-0.15

# LibreTranslate base URL (public instance)
LIBRETRANSLATE_URL=https://libretranslate.com

# Allowed frontend origin
FRONTEND_ORIGIN=http://localhost:5173

# Storage paths (will be created if missing)
STORAGE_AUDIO=backend/storage/audio
STORAGE_VIDEO=backend/storage/videos
```

Install Python deps:

```
python -m venv .venv
.venv/Scripts/activate
pip install -r backend/requirements.txt
```

Run FastAPI dev server:

```
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend
```

2) Frontend

Copy env file:

```
cp frontend/.env.example frontend/.env
```

Install dependencies and run:

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## How It Works

- Frontend uses `getUserMedia` to capture camera + mic. It shows live video.
- Audio is recorded in small chunks with `MediaRecorder` and sent to backend `/api/chunk`.
- Backend pipeline per chunk:
  1. Transcode to `wav` mono 16k with FFmpeg
  2. ASR via Vosk -> text
  3. Translate via LibreTranslate -> target language
  4. TTS via gTTS -> mp3 bytes
  5. Returns base64 mp3 along with metadata
- Frontend queues returned dubbed audio and plays it in order next to the live video.
- When you click Stop, the frontend uploads the captured video (`.webm`) to backend `/api/video/upload` which saves it under `backend/storage/videos/`.

## Notes / Trade-offs

- This is best-effort sync: dubbed audio is played as chunks arrive. Perfect lip-sync is out of scope.
- Public LibreTranslate/G-TTS may have rate limits or latency; you can swap to other providers (Azure, Google Cloud, ElevenLabs) by replacing the service modules.
- Vosk ASR is local and offline but needs model downloads; quality depends on model and environment noise.

## API Overview

- POST `/api/session/start` -> `{ session_id }`
- POST `/api/chunk` (multipart form): `audio` (blob), `client_ts` (ms), `source_lang`, `target_lang`, `session_id`
  - returns JSON with `text`, `translated_text`, `audio_b64`, `mime`, `client_ts`
- POST `/api/session/stop` -> `{ ok: true }`
- POST `/api/video/upload` (multipart): `video` (webm blob), `session_id` -> saved file path

## Credits / References

- Inspired by:
  - QuentinFuxa/WhisperLiveKit
  - KevKibe/RealTime-Voice-Translation-using-Whisper
  - Softcatala/open-dubbing
  - am-sokolov/videodubber
  - Azure-Samples/realtime-translation
  - Awaisn25/RealtimeASR

## Demo

Record a short (3–5 min) screencast:
- Start session, speak in source language
- See translated dubbed audio play along with your live video
- Stop session, which uploads and stores your `.webm` video under `backend/storage/videos/`

