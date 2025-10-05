import json
from typing import Optional
from vosk import Model, KaldiRecognizer
import wave
from pathlib import Path

class VoskASR:
    def __init__(self, model_path: str):
        if not model_path or not Path(model_path).exists():
            raise RuntimeError(f"Vosk model path not found: {model_path}")
        self.model = Model(model_path)

    def transcribe_wav(self, wav_path: str) -> str:
        # Expect mono 16kHz WAV
        with wave.open(wav_path, "rb") as wf:
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                raise ValueError("WAV must be mono PCM16")
            rec = KaldiRecognizer(self.model, wf.getframerate())
            rec.SetWords(False)
            text_parts = []
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    if res.get("text"):
                        text_parts.append(res["text"])
            final = json.loads(rec.FinalResult())
            if final.get("text"):
                text_parts.append(final["text"])
            return " ".join(tp for tp in text_parts if tp).strip()
