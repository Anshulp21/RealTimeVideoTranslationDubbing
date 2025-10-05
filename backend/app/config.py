import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the backend directory
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=False)

class Settings:
    ASR_PROVIDER: str = os.getenv("ASR_PROVIDER", "vosk").lower()
    VOSK_MODEL_PATH: str = os.getenv("VOSK_MODEL_PATH", "")
    LIBRETRANSLATE_URL: str = os.getenv("LIBRETRANSLATE_URL", "https://libretranslate.com")
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    STORAGE_AUDIO: str = os.getenv("STORAGE_AUDIO", "backend/storage/audio")
    STORAGE_VIDEO: str = os.getenv("STORAGE_VIDEO", "backend/storage/videos")
    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", "voxtral-mini-latest")
    MISTRAL_API_URL: str = os.getenv("MISTRAL_API_URL", "https://api.mistral.ai/v1/chat/completions")

    def ensure_storage(self):
        Path(self.STORAGE_AUDIO).mkdir(parents=True, exist_ok=True)
        Path(self.STORAGE_VIDEO).mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.ensure_storage()
