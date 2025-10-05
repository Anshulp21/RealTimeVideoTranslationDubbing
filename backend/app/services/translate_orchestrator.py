import logging
from typing import Optional

from .translate_libre import LibreTranslate
try:
    from .translate_argos import ArgosTranslate
    ARGOS_OK = True
except Exception:
    ARGOS_OK = False


def _mask(s: Optional[str]) -> str:
    if not s:
        return ""
    if len(s) <= 5:
        return "***"
    return s[:3] + "***" + s[-2:]


class TranslatorOrchestrator:
    """Try multiple translators for robustness and free usage.

    Order:
      1) LibreTranslate (JSON, multi-host, optional api_key)
         - Its implementation already falls back to MyMemory when needed.
      2) ArgosTranslate (offline), installs model on first use if available.
    """

    def __init__(self, libre: LibreTranslate, argos: Optional[ArgosTranslate] = None):
        self.logger = logging.getLogger("rt_dub")
        self.libre = libre
        self.argos = argos if ARGOS_OK else None

        # Startup diagnostics (masked)
        try:
            import os
            urls = os.getenv("LIBRETRANSLATE_URL", "https://libretranslate.com")
            key = os.getenv("LIBRETRANSLATE_API_KEY", "")
            self.logger.info(
                "translator.config libre_urls=%s api_key=%s argos=%s",
                urls,
                _mask(key),
                bool(self.argos),
            )
        except Exception:
            pass

    def translate(self, text: str, source: str, target: str) -> str:
        if not text:
            return ""
        # 1) Libre + internal MyMemory fallback
        try:
            out = self.libre.translate(text, source, target)
            # If out equals input and language differs, treat as failure and fall back
            if out and (out != text or (source == target)):
                return out
            self.logger.warning("translator.libre.no_change falling back text_len=%d", len(text))
        except Exception as e:
            self.logger.warning("translator.libre.failed err=%s", e)

        # 2) Argos offline
        if self.argos:
            try:
                out = self.argos.translate(text, source, target)
                if out:
                    return out
            except Exception as e:
                self.logger.warning("translator.argos.failed err=%s", e)

        # 3) Give up — return original text
        return text
