import base64
import logging
from typing import Optional, List, Dict

import requests


class MistralASR:
    """ASR client using Mistral's VoxTral chat-completions endpoint."""

    def __init__(self, api_key: str, model: str = "voxtral-mini-latest", api_url: str = "https://api.mistral.ai/v1/chat/completions", timeout: float = 45.0):
        if not api_key:
            raise ValueError("Mistral API key is required for Mistral ASR")
        self.api_key = api_key
        self.model = model or "voxtral-mini-latest"
        self.api_url = api_url or "https://api.mistral.ai/v1/chat/completions"
        self.timeout = timeout
        self.logger = logging.getLogger("rt_dub")

    def _parse_response(self, payload: Dict) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        first = choices[0] or {}
        message = first.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            texts: List[str] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"text", "output_text"}:
                    txt = part.get("text") or part.get("content") or ""
                    if txt:
                        texts.append(str(txt).strip())
            return " ".join(t for t in texts if t).strip()
        if isinstance(content, str):
            return content.strip()
        # Some responses may place text directly on the message
        if isinstance(message.get("text"), str):
            return message["text"].strip()
        return ""

    def transcribe_wav(self, wav_path: str, prompt: Optional[str] = None) -> str:
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        instruction = prompt or "Transcribe the audio accurately. Respond with only the transcript." 
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_audio", "input_audio": audio_b64},
                        {"type": "text", "text": instruction}
                    ]
                }
            ]
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(self.api_url, json=payload, headers=headers, timeout=self.timeout)
        try:
            resp.raise_for_status()
        except Exception as exc:
            self.logger.error("mistral.asr.http_failed status=%s err=%s body=%s", resp.status_code, exc, resp.text[:500])
            raise
        data = resp.json()
        text = self._parse_response(data)
        if not text:
            self.logger.warning("mistral.asr.empty_response payload_keys=%s", list(data.keys()))
        return text
