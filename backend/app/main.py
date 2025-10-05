import base64
import os
import shutil
import time
import uuid
from pathlib import Path
import logging

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .models.schemas import SessionStartResponse, ChunkResponse, StopResponse
from .services.asr_vosk import VoskASR
from .services.asr_mistral import MistralASR
from .services.translate_libre import LibreTranslate
from .services.translate_orchestrator import TranslatorOrchestrator
try:
    from .services.translate_argos import ArgosTranslate
    _ARGOS_AVAIL = True
except Exception:
    _ARGOS_AVAIL = False
from .services.tts_gtts import GTTSService
from .utils.audio import transcode_to_wav_mono_16k
from .services.render_ffmpeg import render_final_video

app = FastAPI(title="Real-Time Video Translation & Dubbing")

# Logging
logger = logging.getLogger("rt_dub")
if not logger.handlers:
    handler = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"]
    ,allow_headers=["*"]
)

# Serve generated files (audio, videos, srt) under /files
try:
    _storage_base = str(Path(settings.STORAGE_AUDIO).parent)
    app.mount("/files", StaticFiles(directory=_storage_base), name="files")
except Exception:
    pass

# Globals / Singletons
ASR = None
# Compose multi-provider translator (Libre -> MyMemory fallback -> Argos offline)
_libre = LibreTranslate(settings.LIBRETRANSLATE_URL)
_argos = ArgosTranslate() if _ARGOS_AVAIL else None
TRANSLATE = TranslatorOrchestrator(_libre, _argos)
TTS = GTTSService()

SESSIONS = {}

@app.on_event("startup")
def load_asr():
    global ASR
    provider = settings.ASR_PROVIDER
    logger.info("Starting up backend. ASR provider=%s", provider)
    if provider == "mistral":
        if not settings.MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY not set but ASR_PROVIDER=mistral")
        ASR = MistralASR(
            api_key=settings.MISTRAL_API_KEY,
            model=settings.MISTRAL_MODEL,
            api_url=settings.MISTRAL_API_URL,
        )
        logger.info("Mistral ASR ready (model=%s)", settings.MISTRAL_MODEL)
    else:
        logger.info("Loading Vosk model from: %s", settings.VOSK_MODEL_PATH)
        if not settings.VOSK_MODEL_PATH or not Path(settings.VOSK_MODEL_PATH).exists():
            raise RuntimeError("VOSK_MODEL_PATH not set or invalid. See backend/.env.example")
        ASR = VoskASR(settings.VOSK_MODEL_PATH)
        logger.info("Vosk model loaded. Backend ready.")

@app.post("/api/session/start", response_model=SessionStartResponse)
async def start_session():
    sid = str(uuid.uuid4())
    SESSIONS[sid] = {
        "created": time.time(),
        "chunks": 0,
        "timeline_ms": 0,
        "segments": [],  # list of {start_ms,end_ms,text,translated_text,audio_path}
        "video_path": ""
    }
    logger.info("session.start sid=%s", sid)
    return SessionStartResponse(session_id=sid)

@app.post("/api/chunk", response_model=ChunkResponse)
async def process_chunk(
    audio: UploadFile = File(...),
    client_ts: int = Form(0),
    source_lang: str = Form("en"),
    target_lang: str = Form("hi"),
    session_id: str = Form("")
):
    logger.info("chunk.endpoint.called sid=%s src=%s tgt=%s ct=%s", session_id, source_lang, target_lang, audio.content_type)
    if session_id not in SESSIONS:
        logger.warning("chunk.invalid_session sid=%s", session_id)
        return JSONResponse(status_code=400, content={"error": "invalid session"})
    session = SESSIONS[session_id]

    content = await audio.read()
    if not content:
        logger.warning("chunk.recv.empty sid=%s", session_id)
        return JSONResponse(status_code=400, content={"error": "empty audio chunk"})
    ct = (audio.content_type or "").lower()
    # Map content-type to file suffix for ffmpeg input
    if "ogg" in ct:
        suffix = ".ogg"
    elif "webm" in ct:
        suffix = ".webm"
    elif "wav" in ct:
        suffix = ".wav"
    elif "mp3" in ct or "mpeg" in ct:
        suffix = ".mp3"
    elif "mp4" in ct or "m4a" in ct:
        suffix = ".mp4"
    else:
        suffix = ".webm"

    tmpdir = None
    text = ""
    logger.info("chunk.recv sid=%s ct=%s bytes=%s suffix=%s client_ts=%s", session_id, audio.content_type, len(content), suffix, client_ts)
    try:
        wav_path, dur, tmpdir = transcode_to_wav_mono_16k(content, suffix)
        logger.info("chunk.transcoded sid=%s wav=%s dur=%.3fs", session_id, wav_path, dur)
        text = ASR.transcribe_wav(wav_path)
        logger.info("chunk.asr sid=%s text='%s'", session_id, text)
    except Exception as e:
        logger.exception("chunk.error.asr sid=%s err=%s", session_id, e)
        # Cleanup tmpdir if created
        if tmpdir:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
        return JSONResponse(status_code=500, content={"error": f"ASR failed: {e}"})

    # Establish timing for this chunk regardless of ASR text (keeps timeline aligned)
    start_ms = int(session.get("timeline_ms", 0))
    add_ms = int(max(200, dur * 1000))  # minimum 200ms for stability
    end_ms = start_ms + add_ms
    session["timeline_ms"] = end_ms

    # If ASR produced no text, skip translation & TTS to avoid empty audio, but advance timeline
    if not text:
        logger.info("chunk.asr.empty sid=%s -> skipping translate/tts", session_id)
        session["chunks"] += 1
        if tmpdir:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
        return ChunkResponse(
            text="",
            translated_text="",
            audio_b64="",
            mime="",
            client_ts=client_ts
        )

    try:
        translated = TRANSLATE.translate(text, source_lang, target_lang) if text else ""
        logger.info("chunk.translate sid=%s src=%s tgt=%s out_len=%d", session_id, source_lang, target_lang, len(translated))
    except Exception as e:
        logger.exception("chunk.error.translate sid=%s err=%s", session_id, e)
        translated = ""

    try:
        audio_bytes = TTS.synthesize(translated or text, target_lang)
        mime = "audio/mpeg"
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        logger.info("chunk.tts sid=%s bytes=%d mime=%s", session_id, len(audio_bytes), mime)
    except Exception as e:
        logger.exception("chunk.error.tts sid=%s err=%s", session_id, e)
        # Cleanup tmpdir on error
        if tmpdir:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
        return JSONResponse(status_code=500, content={"error": f"TTS failed: {e}"})

    # Optionally store synthesized audio
    ts = int(time.time()*1000)
    out_path = Path(settings.STORAGE_AUDIO) / f"{session_id}_{ts}.mp3"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(audio_b64))
    except Exception:
        pass

    # Record segment for later rendering
    try:
        session["segments"].append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text,
            "translated_text": translated,
            "audio_path": str(out_path)
        })
    except Exception as e:
        logger.warning("segment.append.failed sid=%s err=%s", session_id, e)

    session["chunks"] += 1
    logger.info("chunk.done sid=%s chunks=%d", session_id, session["chunks"])

    # Cleanup tmpdir after successful processing
    if tmpdir:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    return ChunkResponse(
        text=text,
        translated_text=translated,
        audio_b64=audio_b64,
        mime=mime,
        client_ts=client_ts
    )

def _mask(s: str) -> str:
    if not s:
        return ""
    return (s[:3] + "***" + s[-2:]) if len(s) > 5 else "***"

@app.get("/api/health/translate")
async def health_translate(src: str = "en", tgt: str = "hi"):
    """Lightweight diagnostics for translator providers. Keys are masked in response."""
    import os as _os
    diag = {
        "libre": {
            "urls": _os.getenv("LIBRETRANSLATE_URL", "https://libretranslate.com"),
            "api_key_masked": _mask(_os.getenv("LIBRETRANSLATE_API_KEY", "")),
            "ok": False,
        },
        "mymemory": {"ok": False},
        "argos": {"available": bool(_ARGOS_AVAIL), "ok": False},
    }
    sample = "hello"
    # Libre (includes internal fallbacks)
    try:
        out = _libre.translate(sample, src, tgt)
        diag["libre"]["ok"] = bool(out)
    except Exception:
        diag["libre"]["ok"] = False
    # MyMemory direct check
    try:
        import requests as _req
        r = _req.get("https://api.mymemory.translated.net/get", params={"q": sample, "langpair": f"{src}|{tgt}"}, timeout=8)
        if r.ok:
            j = r.json()
            diag["mymemory"]["ok"] = bool((j.get("responseData", {}) or {}).get("translatedText"))
    except Exception:
        pass
    # Argos
    if _argos:
        try:
            _argos.ensure_model(src, tgt)
            aout = _argos.translate(sample, src, tgt)
            diag["argos"]["ok"] = bool(aout)
        except Exception:
            diag["argos"]["ok"] = False
    return diag

@app.post("/api/session/stop", response_model=StopResponse)
async def stop_session(session_id: str = Form("")):
    if session_id in SESSIONS:
        del SESSIONS[session_id]
    logger.info("session.stop sid=%s", session_id)
    return StopResponse(ok=True)

@app.post("/api/video/upload")
async def upload_video(video: UploadFile = File(...), session_id: str = Form("")):
    if not session_id:
        return JSONResponse(status_code=400, content={"error": "session_id required"})
    ts = int(time.time()*1000)
    ext = ".webm"
    if video.filename:
        _, ext = os.path.splitext(video.filename)
        if not ext:
            ext = ".webm"
    save_path = Path(settings.STORAGE_VIDEO) / f"{session_id}_{ts}{ext}"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        shutil.copyfileobj(video.file, f)
    logger.info("video.saved sid=%s path=%s size_bytes=%s", session_id, save_path, getattr(video, 'size', 'n/a'))
    # Store path for later rendering
    try:
        if session_id in SESSIONS:
            SESSIONS[session_id]["video_path"] = str(save_path)
    except Exception:
        pass
    # Build public URLs (served under /files)
    base_rel = Path(settings.STORAGE_AUDIO).parent  # backend/storage
    try:
        rel_video = Path(save_path).resolve().relative_to(Path(base_rel).resolve())
        url = f"/files/{rel_video.as_posix()}"
    except Exception:
        url = ""
    return {"saved": str(save_path), "url": url}


@app.post("/api/video/render")
async def render_video(session_id: str = Form(""), burn_subs: int = Form(1)):
    if not session_id or session_id not in SESSIONS:
        return JSONResponse(status_code=400, content={"error": "invalid session"})
    session = SESSIONS[session_id]
    video_path = session.get("video_path")
    segments = session.get("segments", [])
    if not video_path or not Path(video_path).exists():
        return JSONResponse(status_code=400, content={"error": "video not uploaded for this session"})
    if not segments:
        return JSONResponse(status_code=400, content={"error": "no audio segments to render"})
    try:
        final_path, srt_path = render_final_video(video_path, segments, out_dir=settings.STORAGE_VIDEO, use_translated=True, burn_subs=bool(burn_subs))
        base_rel = Path(settings.STORAGE_AUDIO).parent  # backend/storage
        rel_final = Path(final_path).resolve().relative_to(Path(base_rel).resolve())
        rel_srt = Path(srt_path).resolve().relative_to(Path(base_rel).resolve())
        return {
            "final_path": final_path,
            "srt_path": srt_path,
            "final_url": f"/files/{rel_final.as_posix()}",
            "srt_url": f"/files/{rel_srt.as_posix()}"
        }
    except Exception as e:
        logger.exception("render.failed sid=%s err=%s", session_id, e)
        return JSONResponse(status_code=500, content={"error": f"render failed: {e}"})
