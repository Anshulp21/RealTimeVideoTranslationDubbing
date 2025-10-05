import requests
import os
import logging

class LibreTranslate:
    def __init__(self, base_url: str = "https://libretranslate.com"):
        # Allow comma-separated list in env to try multiple public instances
        # Example: "https://libretranslate.com,https://libretranslate.de"
        raw = os.getenv("LIBRETRANSLATE_URL", base_url)
        parts = [p.strip().rstrip('/') for p in raw.split(',') if p.strip()]
        # Provide sane defaults if single URL fails
        defaults = [
            "https://libretranslate.com",
            "https://libretranslate.de",
            "https://translate.argosopentech.com"
        ]
        # Ensure uniqueness while preserving order
        seen = set()
        self.base_urls = []
        for u in parts + defaults:
            if u and u not in seen:
                self.base_urls.append(u)
                seen.add(u)
        self.logger = logging.getLogger("rt_dub")

    def translate(self, text: str, source: str, target: str) -> str:
        if not text:
            return ""
        payload = {
            "q": text,
            "source": source or "auto",
            "target": target,
            "format": "text"
        }
        api_key = os.getenv("LIBRETRANSLATE_API_KEY", "").strip()
        if api_key:
            payload["api_key"] = api_key
        headers = {"Content-Type": "application/json"}
        last_err = None
        for base in self.base_urls:
            url = f"{base}/translate"
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=12)
                if resp.status_code == 429:
                    # Rate limited, try next base
                    self.logger.warning("translate.rate_limited base=%s", base)
                    last_err = Exception("rate limited")
                    continue
                resp.raise_for_status()
                data = resp.json()
                out = data.get("translatedText", "")
                if out:
                    return out
                # If empty but 200, fall through to next
                self.logger.warning("translate.empty_response base=%s", base)
                last_err = Exception("empty translate response")
            except Exception as e:
                self.logger.warning("translate.failed base=%s err=%s", base, e)
                last_err = e
                continue
        # Fallback 1: MyMemory (free, rate-limited)
        try:
            pair = f"{(source or 'en')|''}|{target}"
        except Exception:
            pair = f"{source or 'en'}|{target}"
        try:
            mm_url = "https://api.mymemory.translated.net/get"
            r = requests.get(mm_url, params={"q": text, "langpair": f"{source or 'en'}|{target}"}, timeout=10)
            r.raise_for_status()
            j = r.json()
            out = (j.get("responseData", {}) or {}).get("translatedText", "")
            if out:
                self.logger.info("translate.mymemory.used")
                return out
        except Exception as e:
            self.logger.warning("translate.mymemory.failed err=%s", e)
        # All providers failed — return original text so TTS can still run
        self.logger.error("translate.all_failed returning original text. last_err=%s", last_err)
        return text
