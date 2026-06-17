"""
Configuration module for ClingySOCKs Memory.
Loads settings from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).parent.parent
load_dotenv(_project_root / ".env")


# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/clingysocks_memory")

# --- API Keys ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# --- Model Configuration ---
# Defaults come from the centralised model_registry; override via env vars.
from src.model_registry import get_default_model as _default_model, get_configured_providers as _configured_providers

def _resolve_default_llm() -> str:
    """Pick the best default LLM based on what API keys are configured.
    Priority: env override > gemini > openai > claude > grok > openrouter > fallback."""
    configured = _configured_providers()
    # Ordered preference — direct providers first, then aggregators
    for provider in ("gemini", "openai", "claude", "grok", "openrouter"):
        if provider in configured:
            return _default_model(provider)
    return _default_model("gemini")  # absolute fallback

_DEFAULT_LLM = _resolve_default_llm()
NARRATIVE_MODEL = os.getenv("NARRATIVE_MODEL", _DEFAULT_LLM)
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", _DEFAULT_LLM)
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", _DEFAULT_LLM)

# --- Pipeline Settings ---
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "50000"))
TIME_GAP_HOURS = int(os.getenv("TIME_GAP_HOURS", "6"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "16384"))
NARRATIVE_TEMPERATURE = float(os.getenv("NARRATIVE_TEMPERATURE", "0.5"))
EXTRACTION_TEMPERATURE = float(os.getenv("EXTRACTION_TEMPERATURE", "0.2"))

# --- LLM call resilience (harvest pipeline) ---
# All pipeline passes route through src/pipeline/llm_client.py, which applies a
# hard timeout, retry-with-backoff, and a global throttle so a long harvest
# stays sequential and under provider rate limits. These are the primary defense
# against a harvest "stopping partway" on a transient 429 / 5xx / hung call.
# How many times to retry a transient failure (429 / 5xx / timeout) per call.
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "4"))
# Fallback per-call timeout used only when a caller doesn't pass its own.
# (The pipeline passes already pass a per-model timeout via get_llm_timeout.)
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
# Max concurrent harvest LLM calls. Keep at 1 to stay strictly sequential and
# avoid bursting the provider rate limit when chunking a long conversation.
LLM_MAX_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "1"))
# Minimum spacing (seconds) between successive LLM call launches. Default 0 =
# no preemptive throttle; we rely on retry-with-backoff to react to a 429.
# Raise this only on a stricter/free tier that benefits from pacing.
LLM_MIN_REQUEST_INTERVAL = float(os.getenv("LLM_MIN_REQUEST_INTERVAL", "0.0"))
# Exponential backoff base / ceiling (seconds) for transient-failure retries.
LLM_RETRY_BASE_DELAY = float(os.getenv("LLM_RETRY_BASE_DELAY", "2.0"))
LLM_RETRY_MAX_DELAY = float(os.getenv("LLM_RETRY_MAX_DELAY", "60.0"))

# --- Harvest pass toggles & cost bounds ---
# Each enabled pass is an extra billed LLM call per chunk/conversation. Toggle
# off to run a leaner, cheaper harvest. Default ON = current behavior.
ECHO_ENABLED = os.getenv("ECHO_ENABLED", "true").lower() == "true"
FACTUAL_ENABLED = os.getenv("FACTUAL_ENABLED", "true").lower() == "true"
# Factual dedup HINT cap: how many existing entities to inject into the factual
# prompt. Code-side dedup still uses ALL entities — this only bounds prompt size
# (the list grows unboundedly otherwise). 0 = inject none (rely on code dedup).
FACTUAL_DEDUP_HINT_LIMIT = int(os.getenv("FACTUAL_DEDUP_HINT_LIMIT", "150"))
# Edge-building cap: max items PER TYPE sent to the edge LLM, most-recent first.
# Bounds the prompt as total memory grows (old items were linked when stored).
# 0 = no cap (legacy: send the entire accumulated memory every conversation).
EDGE_MAX_ITEMS_PER_TYPE = int(os.getenv("EDGE_MAX_ITEMS_PER_TYPE", "50"))

# --- Embedding / pgvector ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "20"))
EMBEDDINGS_ENABLED = os.getenv("EMBEDDINGS_ENABLED", "false").lower() == "true"

# --- Chunking ---
CHUNK_THRESHOLD_CHARS = 100_000
CHUNK_THRESHOLD_MESSAGES = 100
MIN_CHUNK_MESSAGES = 3
MAX_CHUNK_MESSAGES = 100

# --- Paths ---
DATA_DIR = _project_root / "data"
DATA_DIR.mkdir(exist_ok=True)


