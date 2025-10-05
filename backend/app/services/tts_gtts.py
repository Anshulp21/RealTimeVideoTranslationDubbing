from gtts import gTTS
from io import BytesIO

class GTTSService:
    def synthesize(self, text: str, lang: str) -> bytes:
        if not text:
            return b""
        tts = gTTS(text=text, lang=lang)
        fp = BytesIO()
        tts.write_to_fp(fp)
        return fp.getvalue()
