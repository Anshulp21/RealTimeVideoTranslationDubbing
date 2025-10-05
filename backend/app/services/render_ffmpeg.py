import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Tuple

from .subtitle_builder import write_srt_from_chunks


class RenderError(Exception):
    pass


def _run(cmd: List[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RenderError(f"Command failed ({res.returncode}): {' '.join(shlex.quote(c) for c in cmd)}\nSTDERR:\n{res.stderr[:1000]}")


def _make_dubbed_audio(segments: List[Dict], out_audio_path: str) -> None:
    """
    Build a single dubbed audio track by delaying each TTS chunk to its start time and mixing.
    Segments must contain: start_ms, audio_path.
    """
    if not segments:
        raise RenderError("No segments to render")
    FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

    # Inputs
    inputs: List[str] = []
    filter_entries: List[str] = []
    map_labels: List[str] = []
    input_idx = 0

    for seg in segments:
        apath = seg.get("audio_path")
        if not apath or not Path(apath).exists():
            # Skip missing audio
            continue
        delay = max(0, int(seg.get("start_ms", 0)))
        inputs.extend(["-i", apath])
        # Each input is addressable by its positional index in the cmd list (0..N-1)
        label = f"a{input_idx}"
        # Use adelay in ms and apply to all channels to avoid channel mismatch
        filter_entries.append(f"[{input_idx}:a]adelay={delay}:all=1,volume=1[{label}]")
        map_labels.append(f"[{label}]")
        input_idx += 1

    if not map_labels:
        raise RenderError("No audio streams available from segments")

    filter_graph_parts = filter_entries + [f"{''.join(map_labels)}amix=inputs={len(map_labels)}:normalize=0[aout]"]
    filter_complex = ";".join(filter_graph_parts)

    cmd = [FFMPEG_BIN, "-y", *inputs, "-filter_complex", filter_complex, "-map", "[aout]", "-c:a", "aac", out_audio_path]
    _run(cmd)


def render_final_video(video_path: str, segments: List[Dict], out_dir: str, use_translated: bool = True, burn_subs: bool = True) -> Tuple[str, str]:
    """
    Returns (final_video_path, srt_path)
    """
    video_path = str(video_path)
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    sid = None
    # Try to extract session id from video filename prefix 'sessionid_...'
    try:
        base = Path(video_path).name
        sid = base.split('_')[0]
    except Exception:
        sid = "session"

    # Paths
    srt_path = str(out_dir_p / f"{sid}_subs.srt")
    dubbed_audio_path = str(out_dir_p / f"{sid}_dubbed.m4a")
    final_path = str(out_dir_p / f"{sid}_final.mp4")

    # 1) Write SRT from segments
    write_srt_from_chunks(segments, srt_path, use_translated=use_translated)

    # 2) Build dubbed audio track
    _make_dubbed_audio(segments, dubbed_audio_path)

    # 3) Mux with original video, burn subtitles if requested
    FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

    if burn_subs:
        # On Windows, escaping backslashes in the subtitles filter is needed
        srt_escaped = srt_path.replace('\\', '\\\\')
        vf = f"subtitles='{srt_escaped}':force_style='Fontsize=24,Outline=1,MarginV=30'"
        cmd = [
            FFMPEG_BIN, '-y',
            '-i', video_path,
            '-i', dubbed_audio_path,
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-vf', vf,
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22',
            '-c:a', 'aac',
            '-shortest',
            final_path
        ]
    else:
        cmd = [
            FFMPEG_BIN, '-y',
            '-i', video_path,
            '-i', dubbed_audio_path,
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-shortest',
            final_path
        ]

    _run(cmd)
    return final_path, srt_path
