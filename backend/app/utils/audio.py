import subprocess
import tempfile
import os
from pathlib import Path

# Transcodes given input bytes (e.g., webm/opus) to WAV PCM16 mono 16kHz
# Returns path to temporary wav file (caller should delete) and duration (best-effort)

def transcode_to_wav_mono_16k(input_bytes: bytes, input_suffix: str = ".webm"):
    tmpdir = tempfile.mkdtemp(prefix="rt_dub_")
    in_path = os.path.join(tmpdir, f"in{input_suffix}")
    out_path = os.path.join(tmpdir, "out.wav")
    with open(in_path, "wb") as f:
        f.write(input_bytes)
    # Resolve ffmpeg/ffprobe
    FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")
    FFPROBE_BIN = os.getenv("FFPROBE_BIN", "ffprobe")

    # Force format detection for chunked webm/ogg files
    # Use -f to bypass header parsing issues
    input_format = None
    if input_suffix == ".webm":
        input_format = "webm"
    elif input_suffix == ".ogg":
        input_format = "ogg"
    
    cmd = [FFMPEG_BIN, "-y"]
    if input_format:
        cmd.extend(["-f", input_format])
    cmd.extend([
        "-i", in_path,
        "-ac", "1",
        "-ar", "16000",
        out_path
    ])
    # Run ffmpeg and capture stderr for debugging
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        import logging
        logger = logging.getLogger("rt_dub")
        logger.error("ffmpeg failed: returncode=%d stderr=%s", result.returncode, result.stderr)
        raise RuntimeError(f"FFmpeg transcode failed (exit {result.returncode}): {result.stderr[:500]}")
    # Attempt to probe duration
    dur = 0.0
    try:
        probe = subprocess.run([
            FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", in_path
        ], capture_output=True, text=True)
        if probe.returncode == 0 and probe.stdout.strip():
            dur = float(probe.stdout.strip())
    except Exception:
        pass
    return out_path, dur, tmpdir
