"""
ClingySOCKs Memory API — FastAPI Server

Main entry point. Run with:
    uvicorn api.main:app --reload --port 8100

Or from project root:
    python -m uvicorn api.main:app --reload --port 8100

Environment variables:
    AUTH_PROVIDER  — "local" (default) or "hosted" (managed provider)
    EDITION        — "community" (default) | "standard" | "pro" | "full"
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load .env early — before any module reads os.environ (especially MCP subprocesses)
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.db.session import init_db
from src.edition import EDITION, has_feature, Feature

# ── Mode Detection ───────────────────────────────────
AUTH_PROVIDER = os.getenv("AUTH_PROVIDER", "local").lower().strip()
IS_LOCAL = AUTH_PROVIDER == "local"

# ── LiteLLM global config ─────────────────────────────
import litellm
litellm.drop_params = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""

    print(f"🚀 ClingySOCKs starting — edition={EDITION}, auth={AUTH_PROVIDER}")

    # ── Security Check: warn about fallback secrets ────
    _encryption_key = os.getenv("ENCRYPTION_KEY", "")
    _jwt_secret = os.getenv("JWT_SECRET", "")
    if not _encryption_key or not _jwt_secret:
        missing = []
        if not _encryption_key:
            missing.append("ENCRYPTION_KEY")
        if not _jwt_secret:
            missing.append("JWT_SECRET")
        print(f"⚠️  WARNING: {', '.join(missing)} not set — using insecure fallback(s).")
        print(f"   Set these in .env before deploying to production!")
        if os.getenv("REQUIRE_SECRETS", "").lower() in ("true", "1", "yes"):
            raise RuntimeError(
                f"REQUIRE_SECRETS is enabled but {', '.join(missing)} not set. "
                f"Set them in .env or disable REQUIRE_SECRETS."
            )

    # ── Database Setup ────────────────────────────────
    if IS_LOCAL:
        # Self-hosted: always use .env DATABASE_URL
        print("ℹ️  Using .env DATABASE_URL (self-hosted mode)")
    else:
        # Hosted: try to bundle database from secure vault
        from src.db.session import try_load_vault_database
        vault_db_loaded = try_load_vault_database()
        if vault_db_loaded:
            print("🔗 Vault database loaded successfully")
        else:
            from src.integrations.vault import VAULT_MODE
            if VAULT_MODE == "prod":
                print("⚠️  VAULT_MODE=prod — no active vault database found")
                print("   Configure a database in Settings → Database to get started.")
            else:
                print("ℹ️  Using .env DATABASE_URL (dev mode)")

    init_db()  # gracefully skips if engine is None
    from src.db.session import _engine as current_engine
    if current_engine is not None:
        # Also create auth tables for local mode
        if IS_LOCAL:
            from src.db.auth_models import AppUser, ApiKeyEntry  # noqa: F401 — ensure tables are registered
            from src.db.models import Base
            Base.metadata.create_all(current_engine)
        print("✅ Database ready")
        # Load OAuth tokens from DB into os.environ before MCP boot
        from src.integrations.oauth_store import load_all_tokens_to_env
        token_count = load_all_tokens_to_env()
        if token_count:
            print(f"🔑 {token_count} OAuth token(s) loaded into environment")
    else:
        print("⚠️  App started WITHOUT a database — configure one in Settings")

    # ── MCP Clients ───────────────────────────────────
    mcp_manager = None
    if has_feature(Feature.SOCIAL_MCP) or has_feature(Feature.WEB_SEARCH_MCP) or has_feature(Feature.MEDIA_MCP):
        from src.integrations.mcp_client import mcp_manager
        print("🔌 Initializing MCP Clients...")
        await mcp_manager.connect_all()

    # ── Heartbeat System ──────────────────────────────
    heartbeat_mgr = None
    if has_feature(Feature.HEARTBEAT):
        from src.agent.heartbeat import heartbeat_manager
        heartbeat_mgr = heartbeat_manager
        print("💓 Starting heartbeat system...")
        await heartbeat_mgr.start_all()
    else:
        print("ℹ️  Heartbeat system disabled (community edition)")

    # ── Subconscious Daemon & Agent Scheduler ─────────
    try:
        from src.services.subconscious_daemon import subconscious_daemon
        from src.services.agent_scheduler import agent_scheduler
        await subconscious_daemon.start()
        await agent_scheduler.start()
        print("🧠 Subconscious daemon & scheduler started")
    except Exception as e:
        print(f"⚠️  Failed to start daemon/scheduler (non-fatal): {e}")

    yield

    print("👋 Shutting down")
    try:
        from src.services.agent_scheduler import agent_scheduler
        from src.services.subconscious_daemon import subconscious_daemon
        await agent_scheduler.stop()
        await subconscious_daemon.stop()
    except Exception:
        pass
    if heartbeat_mgr:
        await heartbeat_mgr.stop_all()
    if mcp_manager:
        await mcp_manager.disconnect_all()


app = FastAPI(
    title="ClingySOCKs Memory API",
    description="Relational memory engine for AI agents — warm memory, recall, search, harvest, and graph traversal.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
_default_origins = "http://localhost:5173,http://localhost:3000,http://localhost:3001,http://localhost:5678"
_cors_env = os.getenv("CORS_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in (_cors_env or _default_origins).split(",") if o.strip()]

# Auto-detect Railway: check multiple env vars Railway might set
_on_railway = any(os.getenv(k) for k in ("RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_NAME", "RAILWAY_STATIC_URL"))
if _on_railway and not _cors_env:
    ALLOWED_ORIGINS.append("https://clingysocks-frontend-production.up.railway.app")

print(f"🌐 CORS allowed origins: {ALLOWED_ORIGINS}")

# Use regex to also allow any Railway subdomain as a fallback
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.up\.railway\.app" if not _cors_env else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global exception handlers ────────────────────────


# ── Global exception handlers ────────────────────────
from fastapi.responses import JSONResponse
from src.db.session import DatabaseNotConfiguredError, DatabaseUnavailableError

@app.exception_handler(DatabaseNotConfiguredError)
async def database_not_configured_handler(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc), "error": "database_not_configured"})

@app.exception_handler(DatabaseUnavailableError)
async def database_unavailable_handler(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc), "error": "database_unavailable"})


# ── Core Routes (always available) ───────────────────
from api.routes.memory import router as memory_router
from api.routes.harvest import router as harvest_router
from api.routes.chat import router as chat_router
from api.routes.messages import router as messages_router
from api.routes.conversations import router as conversations_router
from api.routes.personas import router as personas_router
from api.routes.user_profile import router as user_profile_router
from api.routes.voice import router as voice_router
from api.routes.voice_live import router as voice_live_router
from api.routes.models import router as models_router
from api.routes.import_chat import router as import_router
from api.routes.context import router as context_router
from api.routes.admin import router as admin_router
from api.routes.files import router as files_router
from api.routes.auth import router as auth_router
from api.routes.group_chat import router as group_chat_router
from api.routes.group_management import router as group_mgmt_router
from api.routes.public_media import router as public_media_router

app.include_router(memory_router, prefix="/memory", tags=["Memory"])
app.include_router(harvest_router, prefix="/harvest", tags=["Harvest"])
app.include_router(chat_router, prefix="/chat", tags=["Chat"])
app.include_router(messages_router, prefix="/messages", tags=["Messages"])
app.include_router(conversations_router, prefix="/conversations", tags=["Conversations"])
app.include_router(personas_router, prefix="/memory", tags=["Personas"])
app.include_router(user_profile_router, prefix="/user-profile", tags=["User Profile"])
app.include_router(voice_router, prefix="/voice", tags=["Voice"])
app.include_router(voice_live_router, prefix="/voice", tags=["Voice Live"])
app.include_router(models_router, prefix="/models", tags=["Models"])
app.include_router(import_router, prefix="/import", tags=["Import"])
app.include_router(context_router, prefix="/context", tags=["Context"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
app.include_router(files_router, prefix="/files", tags=["Files"])
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
# ── Vault Routes (mode-dependent) ────────────────────
if IS_LOCAL:
    from api.routes.vault_local import router as vault_local_router
    app.include_router(vault_local_router, prefix="/vault", tags=["Vault"])
else:
    from api.routes.vault import router as vault_router
    app.include_router(vault_router, prefix="/vault", tags=["Vault"])
# ── Conditional Routes (edition-gated) ───────────────
if has_feature(Feature.AGENT_TASKS):
    from api.routes.agent_tasks import router as agent_tasks_router
    from api.routes.agent_invoke import router as invoke_router
    from api.routes.agent_push import router as push_router
    app.include_router(agent_tasks_router, prefix="/agent", tags=["Agent"])
    app.include_router(invoke_router, prefix="/invoke", tags=["Invoke"])
    app.include_router(push_router, prefix="/push", tags=["Push"])
app.include_router(group_chat_router, prefix="/chat/group", tags=["Group Chat"])
app.include_router(group_mgmt_router, prefix="/groups", tags=["Group Management"])
app.include_router(public_media_router, prefix="/media", tags=["Public Media"])
# ── Enhanced Memory (orient, timeline, surfacing, etc.) ──
try:
    from api.routes.enhanced_memory import router as enhanced_memory_router
    app.include_router(enhanced_memory_router, prefix="/enhanced", tags=["Enhanced Memory"])
except Exception as e:
    print(f"⚠️  Enhanced memory routes not loaded: {e}")
# ── External Agent Integration (OpenClaw) ──────────────
from api.routes.openclaw import router as openclaw_router
app.include_router(openclaw_router, prefix="/openclaw", tags=["OpenClaw"])
# ── WebSocket endpoint for real-time push ────────────

from fastapi import WebSocket, WebSocketDisconnect
from api.ws_manager import ws_manager

@app.websocket("/ws/{entity_id}")
async def websocket_endpoint(websocket: WebSocket, entity_id: str):
    """WebSocket for real-time agent push messages."""
    await ws_manager.connect(entity_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(entity_id, websocket)


# ── Health & Info ────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "clingysocks-memory-api"}


@app.get("/status")
async def status():
    """Return feature readiness based on configured API keys and services.
    
    The frontend uses this to show users which features are available
    and what they need to configure to unlock more.
    """
    from src.model_registry import get_configured_providers
    from src.config import EMBEDDINGS_ENABLED, NARRATIVE_MODEL, EXTRACTION_MODEL, SYNTHESIS_MODEL
    from src.db.session import _engine as current_engine

    configured = get_configured_providers()
    has_chat_provider = any(p in configured for p in ("gemini", "openai", "claude", "grok", "openrouter"))
    has_gemini = "gemini" in configured
    has_tts = "elevenlabs" in configured or bool(os.getenv("GOOGLE_TTS_API_KEY")) or bool(os.getenv("LOCAL_TTS_URL"))
    has_openai_embed = "openai" in configured

    features = {
        "database": current_engine is not None,
        "chat": has_chat_provider,
        "harvest": has_chat_provider,
        "voice_live": has_gemini,
        "tts": has_tts,
        "embeddings": EMBEDDINGS_ENABLED and has_openai_embed,
    }

    hints = []
    if not features["database"]:
        hints.append("Set DATABASE_URL to connect to PostgreSQL with pgvector.")
    if not features["chat"]:
        hints.append("Add at least one LLM API key (OPENROUTER_API_KEY is the easiest) to enable chat and harvest.")
    if not features["voice_live"]:
        hints.append("Voice mode requires GEMINI_API_KEY for real-time audio.")
    if not features["tts"]:
        hints.append("For text-to-speech, add ELEVENLABS_API_KEY, GOOGLE_TTS_API_KEY, or LOCAL_TTS_URL.")
    if EMBEDDINGS_ENABLED and not has_openai_embed:
        hints.append("Embeddings are enabled but OPENAI_API_KEY is missing (needed for text-embedding-3-small).")

    return {
        "features": features,
        "configured_providers": configured,
        "pipeline_models": {
            "narrative": NARRATIVE_MODEL,
            "extraction": EXTRACTION_MODEL,
            "synthesis": SYNTHESIS_MODEL,
        },
        "hints": hints,
    }


@app.get("/info")
async def info():
    """Return edition, auth mode, and available features."""
    from src.edition import get_edition, get_available_features
    return {
        "edition": get_edition(),
        "auth_provider": AUTH_PROVIDER,
        "features": get_available_features(),
    }
