"""VEDA's voice: free neural text-to-speech (Microsoft Edge "Read Aloud" voices via edge-tts),
cached on disk so repeated phrases play instantly. The browser falls back to its own voices
if this service is unreachable.
"""
import asyncio
import hashlib
import logging

from .config import DATA_DIR, env

log = logging.getLogger("finverse.voice")

NAME = "VEDA"
TTS_DIR = DATA_DIR / "tts"
TTS_DIR.mkdir(exist_ok=True)

VOICES = [
    ("en-IN-NeerjaExpressiveNeural", "Neerja · Indian English · expressive"),
    ("en-IN-NeerjaNeural", "Neerja · Indian English"),
    ("en-IN-PrabhatNeural", "Prabhat · Indian English · male"),
    ("en-US-AvaMultilingualNeural", "Ava · American · warm"),
    ("en-US-AndrewMultilingualNeural", "Andrew · American · male"),
    ("en-GB-SoniaNeural", "Sonia · British"),
    ("en-GB-RyanNeural", "Ryan · British · male"),
    ("hi-IN-SwaraNeural", "Swara · Hindi"),
    ("hi-IN-MadhurNeural", "Madhur · Hindi · male"),
]
DEFAULT_VOICE = env("VEDA_VOICE", "en-IN-NeerjaExpressiveNeural")
VALID = {v for v, _ in VOICES}

# Short phrases pre-rendered at startup so VEDA can acknowledge instantly while she works
ACKS = ["Let me check the tape.", "One moment.", "Pulling that up now.", "Right, let me look.", "Give me a second."]
GREETS = ["Yes?", "I'm listening.", "Go ahead."]
MISSES = ["Sorry, I didn't catch that.", "I couldn't reach the data just now."]

_state = {"ok": None, "err": ""}
_locks: dict[str, asyncio.Lock] = {}


def _key(text: str, voice: str, rate: str, pitch: str) -> str:
    return hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode()).hexdigest()


async def synth(text: str, voice: str | None = None, rate: str = "+2%", pitch: str = "-1Hz") -> bytes:
    import edge_tts

    text = " ".join(text.split())[:600]
    voice = voice if voice in VALID else DEFAULT_VOICE
    key = _key(text, voice, rate, pitch)
    path = TTS_DIR / f"{key}.mp3"
    if path.exists():
        return path.read_bytes()
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:  # identical concurrent requests synthesize once
        if path.exists():
            return path.read_bytes()
        chunks = []
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        async for ch in comm.stream():
            if ch["type"] == "audio":
                chunks.append(ch["data"])
        audio = b"".join(chunks)
        if not audio:
            raise RuntimeError("empty audio")
        path.write_bytes(audio)
        _state.update(ok=True, err="")
        return audio


async def warmup(health):
    """Pre-render the acknowledgement phrases for the default voice."""
    try:
        for phrase in ACKS + GREETS + MISSES:
            await synth(phrase)
        health.ok(f"{NAME} · {DEFAULT_VOICE}")
    except Exception as e:
        _state.update(ok=False, err=str(e)[:120])
        health.fail(f"neural voice unreachable ({type(e).__name__}) — browser voices in use")
        return 1800
    return 24 * 3600


def config() -> dict:
    return {"name": NAME, "voices": [{"id": v, "label": l} for v, l in VOICES], "default": DEFAULT_VOICE,
            "neural": _state["ok"] is not False, "acks": ACKS, "greets": GREETS, "misses": MISSES,
            "credit": "Avatar: 'Infinite, 3D Head Scan' by Lee Perry-Smith (CC BY 3.0) · Voices: Microsoft neural TTS"}
