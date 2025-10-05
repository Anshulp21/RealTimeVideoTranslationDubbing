from pydantic import BaseModel

class SessionStartResponse(BaseModel):
    session_id: str

class ChunkResponse(BaseModel):
    text: str
    translated_text: str
    audio_b64: str
    mime: str
    client_ts: int

class StopResponse(BaseModel):
    ok: bool
