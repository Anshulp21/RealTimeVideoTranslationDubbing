# Troubleshooting Guide

## Symptom: No audio chunks reach backend (no transcription/translation)

### Check 1: Browser Console Logs

Open DevTools (F12) → Console. After clicking "Start Translation", you should see:

```
[media] requesting user media (video+audio)
[media] streams ready { audioTracks: 1, videoTracks: 1 }
[rec] audio mime selected: audio/webm;codecs=opus (or similar)
[rec] video mime selected: video/webm;codecs=vp9 (or similar)
[rec] about to start recorders { audioState: 'inactive', videoState: 'inactive' }
[rec] video.start() called, state: recording
[rec] audio.start(2000) called, state: recording
[rec] both recorders started successfully
[rec] audio started
[rec] video started
```

Then every 2 seconds while speaking:
```
[rec] audio ondataavailable fired { hasData: true, size: XXXXX, running: true }
[chunk] sending audio chunk to backend { size: XXXXX, type: 'audio/webm', sessionId: '...' }
[chunk] resp { text: '...', translated_text: '...', audio_b64: '...' }
[chunk] enqueuing dubbed audio { size: YYYY, type: 'audio/mpeg' }
```

### Check 2: Backend Terminal Logs

In your backend terminal (where uvicorn runs), you should see:

```
[TIMESTAMP] INFO rt_dub: session.start sid=...
```

Then for each audio chunk:
```
[TIMESTAMP] INFO rt_dub: chunk.endpoint.called sid=... src=en tgt=hi ct=audio/webm
[TIMESTAMP] INFO rt_dub: chunk.recv sid=... ct=audio/webm bytes=XXXXX suffix=.webm client_ts=...
[TIMESTAMP] INFO rt_dub: chunk.transcoded sid=... wav=... dur=X.XXXs
[TIMESTAMP] INFO rt_dub: chunk.asr sid=... text='your spoken words here'
[TIMESTAMP] INFO rt_dub: chunk.translate sid=... src=en tgt=hi out_len=XX
[TIMESTAMP] INFO rt_dub: chunk.tts sid=... bytes=YYYY mime=audio/mpeg
[TIMESTAMP] INFO rt_dub: chunk.done sid=... chunks=1
```

### Diagnosis

**If you DON'T see** `[rec] audio ondataavailable fired` in browser console:
- MediaRecorder is not capturing audio chunks
- **Fix:**
  1. Ensure microphone permission is granted (check browser site settings)
  2. Ensure the correct input device is selected (browser may default to a different mic)
  3. Check Windows Privacy Settings → Microphone → Allow apps to access
  4. Try a different browser (Chrome/Edge recommended)

**If you see** `[rec] audio ondataavailable fired` with `size: 0` or `hasData: false`:
- MediaRecorder is running but producing empty chunks
- **Fix:**
  1. Check system microphone isn't muted
  2. Test mic in Windows Sound settings → Recording devices → speak and see if green bars move
  3. Close other apps using the microphone
  4. Try incognito/private window

**If you see** `[chunk] sending audio chunk` in browser but NO `chunk.endpoint.called` in backend:
- Network issue or CORS problem
- **Fix:**
  1. Check backend is running on http://localhost:8000
  2. Check frontend .env has `VITE_API_BASE_URL=http://localhost:8000`
  3. Check CORS origins in backend/.env: `FRONTEND_ORIGIN=http://localhost:5173`
  4. Look for 4xx/5xx errors in browser Network tab (F12 → Network)

**If you see** `chunk.endpoint.called` but then `chunk.error.asr`:
- FFmpeg path issue or Vosk model problem
- **Fix:**
  1. Ensure FFmpeg is on PATH or set in backend/.env:
     ```
     FFMPEG_BIN=E:\path\to\ffmpeg.exe
     FFPROBE_BIN=E:\path\to\ffprobe.exe
     ```
  2. Test FFmpeg: `ffmpeg -version` in terminal
  3. Check Vosk model path in backend/.env exists and contains model files

**If you see** `chunk.asr.empty`:
- ASR returns no text (silence, background noise, or short utterance)
- **Fix:**
  1. Speak clearly for 3+ seconds
  2. Reduce background noise
  3. Increase chunk duration in App.jsx: change `audioRec.start(2000)` to `audioRec.start(4000)`

## Symptom: MediaRecorder fails to start (NotSupportedError)

**Error:** `NotSupportedError: Failed to execute 'start' on 'MediaRecorder'`

**Cause:** Unsupported MIME type or missing audio/video track

**Fix:**
1. Check supported codecs in browser console:
   ```javascript
   MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
   MediaRecorder.isTypeSupported('audio/webm')
   MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
   MediaRecorder.isTypeSupported('video/webm')
   ```
2. If all return `false`, your browser build may be incomplete. Try:
   - Update browser to latest version
   - Use Chrome or Edge (best WebRTC support)
   - Check if hardware acceleration is disabled (Settings → System → Use hardware acceleration)

## Symptom: FFmpeg not found

**Error in backend logs:** `FileNotFoundError: ffmpeg` or transcode fails

**Fix:**
1. Download FFmpeg from https://www.gyan.dev/ffmpeg/builds/ (Windows)
2. Extract and add `bin/` to PATH, OR
3. Set explicit paths in `backend/.env`:
   ```
   FFMPEG_BIN=E:\path\to\ffmpeg-xxx\bin\ffmpeg.exe
   FFPROBE_BIN=E:\path\to\ffmpeg-xxx\bin\ffprobe.exe
   ```
4. Restart backend (uvicorn)

## Symptom: Empty audio playback / silent output

**Cause:** TTS returns empty audio or browser audio element muted

**Fix:**
1. Check backend logs for `chunk.tts bytes=XXX` — if bytes=0 or very small, TTS failed
2. Check gTTS language code matches your target language (e.g., `hi` for Hindi)
3. Unmute browser site sound (click sound icon in address bar)
4. Check system volume
5. Test audio element in console:
   ```javascript
   document.querySelector('audio').volume = 1.0
   document.querySelector('audio').muted = false
   ```

## Symptom: Vosk model not loading

**Error:** `RuntimeError: VOSK_MODEL_PATH not set or invalid`

**Fix:**
1. Download a Vosk model from https://alphacephei.com/vosk/models
   - For English: `vosk-model-small-en-us-0.15`
2. Extract to a folder, e.g., `backend/models/vosk-model-small-en-us-0.15`
3. Set path in `backend/.env`:
   ```
   VOSK_MODEL_PATH=./models/vosk-model-small-en-us-0.15
   ```
   (relative to `backend/` directory)
4. Restart backend

## Quick Diagnostic Commands

### Backend
```bash
cd backend
.venv\Scripts\activate
# Check FFmpeg
ffmpeg -version
# Check env vars
echo $env:VOSK_MODEL_PATH
echo $env:FFMPEG_BIN
# Run with verbose logs
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug
```

### Frontend
```bash
cd frontend
npm run dev
# Open http://localhost:5173
# Open DevTools (F12) → Console
# Click Start Translation and speak for 5 seconds
# Watch for [rec] and [chunk] logs
```

### Test Microphone
In browser console:
```javascript
navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
  console.log('Mic OK, tracks:', stream.getAudioTracks())
  stream.getTracks().forEach(t => t.stop())
}).catch(err => console.error('Mic failed:', err))
```

## Still Not Working?

Capture and share:
1. **Browser console logs** (all lines starting with `[media]`, `[rec]`, `[chunk]`)
2. **Backend terminal logs** (last 20 lines including startup and any chunk processing)
3. **Network tab** (F12 → Network, filter by `/api/`, show failed requests)
4. Screenshot of browser site permissions (click padlock in address bar)

With these, we can pinpoint the exact failure point.
