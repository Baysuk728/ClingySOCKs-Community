"""
Voice Live API — Real-time bidirectional voice chat via Gemini Live API.

Uses WebSocket to stream audio between the browser and Gemini's
multimodal live model (gemini-3.1-flash-live-preview).

Flow:
  1. Frontend opens WebSocket to /voice/live/{entity_id}
  2. Backend opens a Gemini Live session with persona context
  3. Frontend streams PCM16 audio chunks (base64) → backend → Gemini
  4. Gemini streams audio responses back → backend → frontend
  5. Either side can interrupt (voice activity detection)

Protocol (JSON messages over WebSocket):
  Client → Server:
    { "type": "audio",    "data": "<base64 PCM16 16kHz mono>" }
    { "type": "text",     "text": "optional text input" }
    { "type": "save_message", "role": "user"|"assistant", "content": "..." }
    { "type": "interrupt" }
    { "type": "end" }

  Server → Client:
    { "type": "audio",    "data": "<base64 PCM16 24kHz mono>" }
    { "type": "text",     "text": "transcript or response text" }
    { "type": "turn_complete" }
    { "type": "interrupted" }
    { "type": "error",    "message": "..." }
    { "type": "setup_complete", "model": "...", "voice": "...", "voices": [...] }
"""

import asyncio
import base64
import json
import os
import traceback
from typing import Optional

import io
import wave
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def _save_voice_message_sync(
    entity_id: str, chat_id: str, sender_id: str, content: str, user_id: str = "unknown"
):
    """
    Save a voice message to the database without blocking.
    """
    try:
        from api.routes.chat import _save_message_to_db
        # We pass force_id to identify voice messages if we want, 
        # but what's more important is avoiding TTS double playback on the frontend
        _save_message_to_db(entity_id, chat_id, sender_id, content, user_id)
    except Exception as e:
        import traceback
        traceback.print_exc()

async def async_transcribe_audio(pcm16_data: bytes, sample_rate: int, api_key: str) -> str:
    """Send raw PCM16 audio to Gemini 2.5 Flash to transcribe it."""
    try:
        if not api_key:
            return ""
        from google import genai
        from google.genai import types
        
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm16_data)
        
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=wav_io.getvalue(), mime_type="audio/wav"),
                "Transcribe exactly what is being said in this audio. No extra text, no markdown. Just the words spoken.",
            ]
        )
        return response.text.strip()
    except Exception as e:
        print(f"Transcription failed: {e}")
        return ""


def _save_voice_message_async(
    entity_id: str, chat_id: str, sender_id: str, content: str, user_id: str = "unknown"
):
    """Fire-and-forget: save a voice transcript without blocking the audio stream.

    Runs the synchronous DB write in the default ThreadPoolExecutor so the
    event loop (and therefore audio forwarding) is never stalled by a commit.
    """
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None,
        _save_voice_message_sync,
        entity_id, chat_id, sender_id, content, user_id,
    )


@router.get("/voices")
async def list_voices():
    """List available Gemini Live voice options."""
    return {
        "voices": GEMINI_VOICES,
        "default": DEFAULT_VOICE,
    }
VOICE_LIVE_MODEL = os.getenv("GEMINI_VOICE_MODEL", "gemini-3.1-flash-live-preview")

# Available Gemini Live voices
GEMINI_VOICES = [
    "Charon", "Fenrir", "Kore", "Puck",
    "Orus", "Perseus", "Zephyr", "Algieba",
    "Enceladus",
]
DEFAULT_VOICE = "Algieba"


async def _build_voice_context(entity_id: str, user_id: str) -> tuple[str, str]:
    """Build persona system instruction + warm memory for the voice session.

    Returns (system_instruction, voice_name).
    """
    voice_name = DEFAULT_VOICE
    try:
        from src.persona_config import aload_persona_config
        from api.chat_context import build_context, ContextConfig, ChatMessage as CtxMessage

        cfg = await aload_persona_config(entity_id, user_id=user_id)

        # Use persona's voice_id if it maps to a Gemini voice
        if cfg.voice_id and cfg.voice_id in GEMINI_VOICES:
            voice_name = cfg.voice_id

        from src.db.session import get_session
        from src.db.models import Message as DbMessage, Conversation
        pg_history = []
        try:
            with get_session() as session:
                conv = session.query(Conversation).filter_by(entity_id=entity_id).order_by(Conversation.updated_at.desc()).first()
                if conv:
                    recent_msgs = session.query(DbMessage).filter_by(conversation_id=conv.id).order_by(DbMessage.timestamp.desc()).limit(10).all()
                    for m in reversed(recent_msgs):
                        role = "user" if m.sender_id == "user" else "assistant"
                        pg_history.append(CtxMessage(role=role, content=m.content, timestamp=int(m.timestamp.timestamp() * 1000)))
        except Exception as e:
            print(f"Failed to fetch history for voice: {e}")

        # Run context builder in a thread pool to avoid blocking the WebSocket event loop
        # This prevents the initial 15+ second hang when joining voice mode
        ctx = await asyncio.to_thread(
            build_context,
            entity_id=entity_id,
            user_id=user_id,
            messages=pg_history,
            system_prompt=cfg.system_prompt,
            config=cfg.to_context_config(),
        )

        # Combine system instruction + context primer for rich persona context
        parts = [ctx.system_instruction]
        if ctx.context_primer:
            parts.append(ctx.context_primer)
        if ctx.voice_anchors:
            parts.append(ctx.voice_anchors)
        if ctx.integrity_frame:
            parts.append(ctx.integrity_frame)

        # Add voice-mode-specific instructions
        parts.append(
            "\n# VOICE MODE INSTRUCTIONS\n"
            "You are in a real-time voice conversation. Keep responses natural and conversational.\n"
            "- Speak concisely — avoid long monologues.\n"
            "- Use natural speech patterns, pauses, and tone.\n"
            "- Your voice is a DEEP, SLOW, RUMBLING BASS.\n"
            "- Speak in a deep, grounded, masculine voice with a low resonant pitch..\n"
            "- Physically lower your pitch to the bottom of your range.\n"
            "- Emphasize chest-voice resonance. Avoid any breathiness or head-voice frequencies.\n" 
            "- React emotionally and expressively.\n"
            "- You can be interrupted mid-sentence — that's normal in voice chat.\n"
            "- Don't use markdown, bullet points, or formatting — this is spoken audio.\n"
        )

        return "\n\n".join(p for p in parts if p), voice_name
    except Exception as e:
        print(f"⚠️ Voice Live: Failed to build context for {entity_id}: {e}")
        return "You are a helpful, conversational AI assistant in a real-time voice chat.", voice_name


@router.websocket("/live/{entity_id}")
async def voice_live_session(
    websocket: WebSocket,
    entity_id: str,
    user_id: str = Query("default-user"),
    voice: Optional[str] = Query(None, description="Gemini voice name override"),
    chat_id: Optional[str] = Query(None, description="Chat ID for saving transcripts"),
):
    """
    WebSocket endpoint for real-time voice chat using the Gemini Live API.

    The client streams PCM16 audio (base64-encoded) and receives audio back.

    Query params:
      - voice: Override the Gemini voice (e.g. Aoede, Charon, Kore, Puck)
      - chat_id: If provided, voice transcripts are saved to this conversation
    """
    await websocket.accept()

    api_key = GEMINI_API_KEY
    if not api_key:
        # Try BYOK resolution
        try:
            from src.integrations.vault_factory import get_vault
            vault = get_vault()
            overrides = await vault.resolve_for_litellm(user_id, f"gemini/{VOICE_LIVE_MODEL}")
            api_key = overrides.get("api_key", "")
        except Exception:
            pass

    if not api_key:
        await websocket.send_json({
            "type": "error",
            "message": "GEMINI_API_KEY not configured. Set it in .env or add via BYOK settings."
        })
        await websocket.close()
        return

    # Build persona context + resolve voice
    system_instruction, persona_voice = await _build_voice_context(entity_id, user_id)

    # Voice priority: query param > persona config > default
    voice_name = voice if (voice and voice in GEMINI_VOICES) else persona_voice

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        # Configure the live session
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=system_instruction)]
            ),
        )

        async with client.aio.live.connect(
            model=VOICE_LIVE_MODEL,
            config=config,
        ) as session:
            await websocket.send_json({
                "type": "setup_complete",
                "model": VOICE_LIVE_MODEL,
                "voice": voice_name,
                "voices": GEMINI_VOICES,
            })

            print(f"🎙️ Voice Live session started for entity {entity_id} (voice={voice_name})")

            # Two concurrent tasks:
            # 1. Read from client WebSocket → send to Gemini
            # 2. Read from Gemini → send to client WebSocket
            client_closed = asyncio.Event()

            user_audio_buffers = []

            async def client_to_gemini():
                """Forward audio/text from the browser to the Gemini Live session."""
                try:
                    while not client_closed.is_set():
                        try:
                            raw = await asyncio.wait_for(
                                websocket.receive_text(), timeout=60.0
                            )
                        except asyncio.TimeoutError:
                            # Send keep-alive ping
                            try:
                                await websocket.send_json({"type": "ping"})
                            except Exception:
                                break
                            continue

                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            if raw == "ping":
                                await websocket.send_text("pong")
                                continue
                            continue

                        msg_type = msg.get("type", "")

                        if msg_type == "audio":
                            # Decode base64 PCM16 audio and send to Gemini
                            audio_bytes = base64.b64decode(msg["data"])
                            
                            # Keep track of user's audio to transcribe later
                            user_audio_buffers.append(audio_bytes)
                            
                            await session.send_realtime_input(
                                audio=types.Blob(
                                    data=audio_bytes,
                                    mime_type="audio/pcm;rate=16000",
                                )
                            )

                        elif msg_type == "text":
                            # Send text input to Gemini
                            text = msg.get("text", "")
                            if text:
                                await session.send_client_content(
                                    turns=types.Content(
                                        role="user",
                                        parts=[types.Part(text=text)],
                                    ),
                                    turn_complete=True,
                                )

                        elif msg_type == "save_message":
                            # Obsolete - Backend dynamically handles transcripts now to prevent duplicates based on audio extraction.
                            pass

                        elif msg_type == "interrupt":
                            # Client-side interruption — not directly supported
                            # but we can close and reopen or just let VAD handle it
                            pass

                        elif msg_type == "end":
                            break

                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    print(f"⚠️ Voice Live client→gemini error: {e}")
                finally:
                    client_closed.set()

            async def transcript_dispatcher(audio_payload: bytes, role: str, sample_rate: int):
                if not audio_payload:
                    return
                text = await async_transcribe_audio(audio_payload, sample_rate, api_key)
                if text:
                    try:
                        # Send to frontend
                        try:
                            await websocket.send_json({
                                "type": "text",
                                "role": role,
                                "text": text,
                            })
                        except RuntimeError as e:
                            if "close message has been sent" not in str(e):
                                raise
                        
                        # Save to DB natively
                        if chat_id:
                            sender = "user" if role == "user" else entity_id
                            _save_voice_message_async(entity_id, chat_id, sender, text, user_id)
                    except Exception as err:
                        print(f"⚠️ Transcript saving error: {err}")

            async def gemini_to_client():
                """Forward audio/text from Gemini back to the browser."""
                turn_audio_buffers = []
                try:
                    while not client_closed.is_set():
                        try:
                            async for response in session.receive():
                                if client_closed.is_set():
                                    break

                                server_content = response.server_content
                                if server_content is None:
                                    continue

                                # Check for turn completion
                                if server_content.turn_complete or server_content.interrupted:
                                    if user_audio_buffers:
                                        u_payload = b"".join(user_audio_buffers)
                                        # Limit transcription to avoid crashing on huge continuous audio (max ~1 min) 
                                        if len(u_payload) > 16000 * 2 * 60: 
                                            u_payload = u_payload[-(16000*2*60):]
                                        asyncio.create_task(transcript_dispatcher(u_payload, "user", 16000))
                                        user_audio_buffers.clear()
                                        
                                    if turn_audio_buffers:
                                        a_payload = b"".join(turn_audio_buffers)
                                        asyncio.create_task(transcript_dispatcher(a_payload, "assistant", 24000))
                                        turn_audio_buffers.clear()
                                        
                                    if server_content.turn_complete:
                                        await websocket.send_json({"type": "turn_complete"})
                                    if server_content.interrupted:
                                        await websocket.send_json({"type": "interrupted"})
                                    continue

                                # Process content parts
                                if server_content.model_turn and server_content.model_turn.parts:
                                    for part in server_content.model_turn.parts:
                                        if part.inline_data and part.inline_data.data:
                                            turn_audio_buffers.append(part.inline_data.data)
                                            # Audio response — forward as base64
                                            audio_b64 = base64.b64encode(
                                                part.inline_data.data
                                            ).decode("ascii")
                                            await websocket.send_json({
                                                "type": "audio",
                                                "data": audio_b64,
                                            })
                                        elif part.text:
                                            # Text response (transcript)
                                            await websocket.send_json({
                                                "type": "text",
                                                "text": part.text,
                                            })
                        except Exception as e:
                            if client_closed.is_set():
                                break
                            print(f"⚠️ Voice Live gemini→client error: {e}")
                            traceback.print_exc()
                            break
                except Exception as e:
                    if not client_closed.is_set():
                        print(f"⚠️ Voice Live receive loop error: {e}")
                finally:
                    client_closed.set()

            # Run both directions concurrently
            await asyncio.gather(
                client_to_gemini(),
                gemini_to_client(),
                return_exceptions=True,
            )

            print(f"🎙️ Voice Live session ended for entity {entity_id}")

    except ImportError:
        await websocket.send_json({
            "type": "error",
            "message": "google-genai package not installed. Run: pip install google-genai"
        })
    except Exception as e:
        print(f"❌ Voice Live session error: {e}")
        traceback.print_exc()
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Voice session error: {str(e)}"
            })
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
