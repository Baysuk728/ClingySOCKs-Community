"""
Voice API — Text-to-Speech synthesis with PostgreSQL audio caching.

Migrated from legacy cloud services (generateSpeech).
Supports 4 providers: Google TTS, OpenAI TTS, ElevenLabs, Local (Kokoro).

Endpoints:
  POST  /voice/synthesize       — Generate or retrieve cached TTS audio
  GET   /voice/audio/{cache_key} — Stream cached audio by key
  GET   /voice/stats             — Cache statistics
  DELETE /voice/cache             — Purge old cache entries
"""

import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.db.session import get_session
from src.db.models import AudioCache

router = APIRouter()

# ─── Config ───────────────────────────────────────────
GOOGLE_TTS_KEY = os.getenv("GOOGLE_TTS_API_KEY") or os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
LOCAL_TTS_URL = os.getenv("LOCAL_TTS_URL", "http://localhost:8880")

MAX_TEXT_LENGTH = 5000  # Cost control


# ─── Request / Response Models ────────────────────────

class SynthesizeRequest(BaseModel):
    text: str = Field(..., max_length=MAX_TEXT_LENGTH, description="Text to synthesize")
    voice_id: str = Field(..., description="Voice name/ID (provider-specific)")
    tts_provider: str = Field("google", description="google | openai | elevenlabs | local")
    entity_id: Optional[str] = Field(None, description="Entity ID (for cache association)")
    # Provider-specific options
    model_id: Optional[str] = Field(None, description="Model ID (ElevenLabs: eleven_turbo_v2_5, OpenAI: tts-1)")
    speed: float = Field(1.0, ge=0.25, le=4.0, description="Playback speed (OpenAI/local)")
    response_format: str = Field("mp3", description="Audio format: mp3, opus, wav")


class SynthesizeResponse(BaseModel):
    audio_url: str          # URL to stream the audio from our API
    cache_key: str          # MD5 cache key
    cached: bool            # Whether it was served from cache
    provider: str
    size_bytes: int


# ─── Main Endpoint ────────────────────────────────────

@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_speech(req: SynthesizeRequest):
    """
    Generate TTS audio or serve from PostgreSQL cache.
    
    Cache key = MD5(sanitized_text + voice_id + provider).
    Audio is stored as binary in the audio_cache table.
    """
    provider = req.tts_provider.lower()
    if provider not in ("google", "openai", "elevenlabs", "local"):
        raise HTTPException(400, f"Unknown TTS provider: {provider}")

    # Sanitize text (strip markdown for speech)
    clean_text = _sanitize_for_tts(req.text)
    if not clean_text.strip():
        raise HTTPException(400, "Text is empty after sanitization")

    # Generate cache key
    cache_key = _make_cache_key(clean_text, req.voice_id, provider)

    # 1. Check cache
    with get_session() as session:
        cached = session.query(AudioCache).filter_by(cache_key=cache_key).first()
        if cached:
            cached.last_accessed_at = datetime.now(timezone.utc)
            cached.access_count = (cached.access_count or 0) + 1
            print(f"🎵 TTS Cache HIT ({provider}): {cache_key[:8]}...")
            return SynthesizeResponse(
                audio_url=f"/voice/audio/{cache_key}",
                cache_key=cache_key,
                cached=True,
                provider=provider,
                size_bytes=cached.audio_size_bytes or 0,
            )

    # 2. Cache MISS — generate audio
    print(f"🎵 TTS Cache MISS ({provider}): {cache_key[:8]}... ({len(clean_text)} chars)")

    try:
        if provider == "google":
            audio_bytes, content_type = await _generate_google(clean_text, req.voice_id)
        elif provider == "openai":
            audio_bytes, content_type = await _generate_openai(
                clean_text, req.voice_id,
                model=req.model_id or "tts-1",
                speed=req.speed,
                fmt=req.response_format,
            )
        elif provider == "elevenlabs":
            audio_bytes, content_type = await _generate_elevenlabs(
                clean_text, req.voice_id,
                model=req.model_id or "eleven_turbo_v2_5",
            )
        elif provider == "local":
            audio_bytes, content_type = await _generate_local(
                clean_text, req.voice_id,
                speed=req.speed,
                fmt=req.response_format,
            )
        else:
            raise HTTPException(400, f"Unsupported provider: {provider}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ TTS generation failed ({provider}): {e}")
        raise HTTPException(500, f"TTS generation failed: {str(e)}")

    # 3. Save to cache
    with get_session() as session:
        entry = AudioCache(
            id=str(uuid.uuid4()),
            cache_key=cache_key,
            entity_id=req.entity_id,
            text_preview=clean_text[:100],
            voice_id=req.voice_id,
            tts_provider=provider,
            audio_data=audio_bytes,
            content_type=content_type,
            audio_size_bytes=len(audio_bytes),
        )
        session.add(entry)

    print(f"✅ TTS Generated & Cached ({provider}): {cache_key[:8]}... ({len(audio_bytes)} bytes)")

    return SynthesizeResponse(
        audio_url=f"/voice/audio/{cache_key}",
        cache_key=cache_key,
        cached=False,
        provider=provider,
        size_bytes=len(audio_bytes),
    )


# ─── Audio Streaming ─────────────────────────────────

@router.get("/audio/{cache_key}")
async def stream_audio(cache_key: str):
    """Stream cached audio by cache key."""
    with get_session() as session:
        entry = session.query(AudioCache).filter_by(cache_key=cache_key).first()
        if not entry:
            raise HTTPException(404, "Audio not found in cache")

        # Update access stats
        entry.last_accessed_at = datetime.now(timezone.utc)
        entry.access_count = (entry.access_count or 0) + 1

        return Response(
            content=entry.audio_data,
            media_type=entry.content_type or "audio/mpeg",
            headers={
                "Cache-Control": "public, max-age=31536000",  # 1 year (content-addressed)
                "Content-Length": str(len(entry.audio_data)),
            },
        )


# ─── Stats / Management ──────────────────────────────

@router.get("/stats")
async def cache_stats(entity_id: Optional[str] = Query(None)):
    """Get cache statistics."""
    with get_session() as session:
        query = session.query(AudioCache)
        if entity_id:
            query = query.filter_by(entity_id=entity_id)

        total = query.count()

        # Sum bytes
        from sqlalchemy import func
        total_bytes = session.query(func.sum(AudioCache.audio_size_bytes)).scalar() or 0

        # By provider
        by_provider = {}
        for row in session.query(AudioCache.tts_provider, func.count()).group_by(AudioCache.tts_provider).all():
            by_provider[row[0]] = row[1]

        return {
            "total_entries": total,
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / 1_048_576, 2),
            "by_provider": by_provider,
        }


@router.delete("/cache")
async def purge_cache(
    older_than_days: int = Query(30, description="Delete entries older than N days"),
    provider: Optional[str] = Query(None, description="Only purge specific provider"),
):
    """Purge old cache entries to reclaim space."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    with get_session() as session:
        query = session.query(AudioCache).filter(AudioCache.last_accessed_at < cutoff)
        if provider:
            query = query.filter_by(tts_provider=provider)

        count = query.count()
        query.delete(synchronize_session="fetch")

    return {"purged": count, "older_than_days": older_than_days}


# ─── Provider Implementations ─────────────────────────

async def _generate_google(text: str, voice_id: str) -> tuple[bytes, str]:
    """Google Cloud TTS via REST API."""
    if not GOOGLE_TTS_KEY:
        raise HTTPException(503, "Google TTS not configured (GEMINI_API_KEY missing)")

    # Extract language code from voice name (e.g., "en-US-Neural2-D" → "en-US")
    parts = voice_id.split("-")
    lang_code = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else "en-US"

    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_TTS_KEY}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json={
            "input": {"text": text},
            "voice": {
                "languageCode": lang_code,
                "name": voice_id,
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": 1.0,
                "pitch": 0.0,
            },
        })

    if resp.status_code != 200:
        body = resp.text
        print(f"❌ Google TTS error ({resp.status_code}): {body[:300]}")
        if resp.status_code == 403:
            raise HTTPException(403, (
                "Google TTS API returned 403 Forbidden. "
                "Your API key likely doesn't have the Cloud Text-to-Speech API enabled. "
                "Enable it at: https://console.cloud.google.com/apis/library/texttospeech.googleapis.com  "
                "Or set GOOGLE_TTS_API_KEY in .env to a key from a project with TTS enabled. "
                "Alternatively, switch the persona's TTS provider to 'openai' which works immediately."
            ))
        raise HTTPException(502, f"Google TTS API error: {resp.status_code}")

    import base64
    audio_content = resp.json().get("audioContent", "")
    return base64.b64decode(audio_content), "audio/mpeg"


async def _generate_openai(
    text: str, voice: str, model: str = "tts-1",
    speed: float = 1.0, fmt: str = "mp3"
) -> tuple[bytes, str]:
    """OpenAI TTS API (tts-1 or tts-1-hd)."""
    if not OPENAI_API_KEY:
        raise HTTPException(503, "OpenAI TTS not configured (OPENAI_API_KEY missing)")

    content_types = {
        "mp3": "audio/mpeg",
        "opus": "audio/opus",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "wav": "audio/wav",
    }

    url = "https://api.openai.com/v1/audio/speech"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": text,
                "voice": voice,
                "speed": speed,
                "response_format": fmt,
            },
        )

    if resp.status_code != 200:
        print(f"❌ OpenAI TTS error: {resp.text}")
        raise HTTPException(502, f"OpenAI TTS API error: {resp.status_code}")

    return resp.content, content_types.get(fmt, "audio/mpeg")


async def _generate_elevenlabs(
    text: str, voice_id: str, model: str = "eleven_turbo_v2_5"
) -> tuple[bytes, str]:
    """ElevenLabs TTS API."""
    if not ELEVENLABS_API_KEY:
        raise HTTPException(503, "ElevenLabs not configured (ELEVENLABS_API_KEY missing)")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            url,
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": model,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
            },
        )

    if resp.status_code != 200:
        print(f"❌ ElevenLabs error: {resp.text}")
        raise HTTPException(502, f"ElevenLabs API error: {resp.status_code}")

    return resp.content, "audio/mpeg"


async def _generate_local(
    text: str, voice: str, speed: float = 1.0, fmt: str = "wav"
) -> tuple[bytes, str]:
    """Local TTS server (Kokoro/Sesame at LOCAL_TTS_URL)."""
    content_types = {"wav": "audio/wav", "mp3": "audio/mpeg", "opus": "audio/opus"}

    url = f"{LOCAL_TTS_URL}/v1/audio/speech"

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json={
                "model": "kokoro",
                "input": text,
                "voice": voice,
                "speed": speed,
                "response_format": fmt,
            })
    except httpx.ConnectError:
        raise HTTPException(503, f"Local TTS server not reachable at {LOCAL_TTS_URL}")

    if resp.status_code != 200:
        print(f"❌ Local TTS error: {resp.text}")
        raise HTTPException(502, f"Local TTS error: {resp.status_code}")

    return resp.content, content_types.get(fmt, "audio/wav")


# ─── Helpers ──────────────────────────────────────────

def _make_cache_key(text: str, voice_id: str, provider: str) -> str:
    """Generate deterministic cache key from text + voice + provider."""
    raw = f"{text}|{voice_id}|{provider}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _sanitize_for_tts(text: str) -> str:
    """Strip markdown, emojis, and non-speech characters for clean TTS output."""
    s = text

    # ── Markdown stripping ─────────────────────────────────
    s = re.sub(r'```[\s\S]*?```', ' code block ', s)       # Code blocks
    s = re.sub(r'`([^`]+)`', r'\1', s)                     # Inline code
    s = re.sub(r'\*\*([^*]+)\*\*', r'\1', s)               # Bold **text**
    s = re.sub(r'__([^_]+)__', r'\1', s)                   # Bold __text__
    s = re.sub(r'~~([^~]+)~~', r'\1', s)                   # Strikethrough
    s = re.sub(r'#+\s*', '', s)                            # Headings
    s = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)         # Links → keep text
    s = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', s)           # Images → remove
    s = re.sub(r'^\s*[-*+]\s+', '', s, flags=re.MULTILINE) # Bullet list markers
    s = re.sub(r'^\s*\d+\.\s+', '', s, flags=re.MULTILINE) # Numbered list markers
    s = re.sub(r'>\s*', '', s)                             # Blockquotes
    s = re.sub(r'\|', ' ', s)                              # Pipes
    s = re.sub(r'---+', ' ', s)                            # Horizontal rules

    # ── Action markers / roleplay asterisks ────────────────
    # *sighs softly* → sighs softly
    s = re.sub(r'\*([^*]+)\*', r'\1', s)                   # Italic / action *text*
    s = re.sub(r'_([^_]+)_', r'\1', s)                     # Italic / action _text_

    # ── Emojis ────────────────────────────────────────────
    # Remove all Unicode emoji characters (TTS reads them as names)
    s = re.sub(
        r'['
        r'\U0001F600-\U0001F64F'  # Emoticons
        r'\U0001F300-\U0001F5FF'  # Misc symbols & pictographs
        r'\U0001F680-\U0001F6FF'  # Transport & map
        r'\U0001F1E0-\U0001F1FF'  # Flags
        r'\U0001FA00-\U0001FA6F'  # Chess, extended-A
        r'\U0001FA70-\U0001FAFF'  # Extended-A continued
        r'\U00002702-\U000027B0'  # Dingbats
        r'\U000024C2-\U0001F251'  # Enclosed chars
        r'\U0000FE00-\U0000FE0F'  # Variation selectors
        r'\U0000200D'              # Zero-width joiner
        r'\U00002600-\U000026FF'  # Misc symbols
        r'\U0000200B-\U0000200F'  # Zero-width spaces
        r'\U0000205F-\U00002060'  # Word joiners
        r'\U00002934-\U00002935'  # Arrows
        r'\u2764'                  # Heart
        r']+',
        '', s
    )

    # ── Quotes & special punctuation ──────────────────────
    # Replace smart/curly quotes with nothing (TTS reads "quote" / "end quote")
    s = s.replace('\u201c', '').replace('\u201d', '')   # " "
    s = s.replace('\u2018', '').replace('\u2019', '')   # ' '
    s = s.replace('\u00ab', '').replace('\u00bb', '')   # « »
    s = re.sub(r'"', '', s)                             # Straight double quotes
    # Keep apostrophes in contractions (don't, it's) but strip lone quotes
    s = re.sub(r"(?<![a-zA-Z])'|'(?![a-zA-Z])", '', s) # Strip non-contraction single quotes
    s = s.replace('\u2026', '...')                       # Ellipsis char → dots
    s = s.replace('\u2014', ', ')                        # Em-dash → comma pause
    s = s.replace('\u2013', ' to ')                      # En-dash → "to"

    # ── URLs that survived link removal ───────────────────
    s = re.sub(r'https?://\S+', '', s)

    # ── Cleanup ───────────────────────────────────────────
    s = re.sub(r'\n{3,}', '\n\n', s)                       # Collapse newlines
    s = re.sub(r'  +', ' ', s)                             # Collapse double spaces
    return s.strip()
