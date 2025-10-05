from typing import List, Dict
import math


def build_segments_from_words(words: List[Dict], max_chars: int = 80, max_dur: float = 3.5, max_gap: float = 0.6) -> List[Dict]:
    """
    Groups Vosk word-level results into subtitle-like segments with start/end times.

    words: list of {"word": str, "start": float, "end": float}
    Returns list of {"start": float, "end": float, "text": str}
    """
    segments: List[Dict] = []
    cur_words: List[Dict] = []
    last_end = None

    def flush():
        nonlocal cur_words
        if not cur_words:
            return
        seg = {
            "start": float(cur_words[0]["start"]),
            "end": float(cur_words[-1]["end"]),
            "text": " ".join(w["word"] for w in cur_words).strip()
        }
        # Ensure minimum duration
        if seg["end"] <= seg["start"]:
            seg["end"] = seg["start"] + 0.8
        segments.append(seg)
        cur_words = []

    for w in words:
        if not w.get("word"):
            continue
        if last_end is not None and (w["start"] - last_end) > max_gap:
            flush()
        cur_words.append({"word": w["word"], "start": w["start"], "end": w["end"]})
        last_end = w["end"]
        # Check limits
        dur = cur_words[-1]["end"] - cur_words[0]["start"]
        chars = sum(len(x["word"]) + 1 for x in cur_words)
        if dur >= max_dur or chars >= max_chars:
            flush()

    flush()
    return segments


def _fmt_srt_time(t: float) -> str:
    # SRT uses comma for ms separator
    ms = int(round(t * 1000))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments: List[Dict], srt_path: str) -> None:
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            start = _fmt_srt_time(max(0.0, float(seg["start"])) )
            end = _fmt_srt_time(max(float(seg["start"]) + 0.2, float(seg["end"])) )
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")


def write_srt_from_chunks(chunks: List[Dict], srt_path: str, use_translated: bool = True) -> None:
    """
    Write SRT from chunk-based segments collected during a session.

    Each chunk is expected to have keys:
      - start_ms: int
      - end_ms: int
      - text: str (original)
      - translated_text: str (translated)
    """
    def _fmt_ms(ms: int) -> str:
        h = ms // 3600000
        ms %= 3600000
        m = ms // 60000
        ms %= 60000
        s = ms // 1000
        ms = ms % 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(srt_path, "w", encoding="utf-8") as f:
        idx = 1
        for seg in chunks:
            text = (seg.get("translated_text") if use_translated else seg.get("text")) or ""
            text = text.strip()
            if not text:
                continue
            start_ms = int(max(0, seg.get("start_ms", 0)))
            end_ms = int(max(start_ms + 200, seg.get("end_ms", start_ms + 800)))
            f.write(f"{idx}\n{_fmt_ms(start_ms)} --> {_fmt_ms(end_ms)}\n{text}\n\n")
            idx += 1
