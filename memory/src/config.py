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
from src.model_registry import get_default_model as _default_model
_DEFAULT_LLM = _default_model("gemini")
NARRATIVE_MODEL = os.getenv("NARRATIVE_MODEL", _DEFAULT_LLM)
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", _DEFAULT_LLM)
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", _DEFAULT_LLM)

# --- Pipeline Settings ---
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "50000"))
TIME_GAP_HOURS = int(os.getenv("TIME_GAP_HOURS", "6"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "16384"))
NARRATIVE_TEMPERATURE = float(os.getenv("NARRATIVE_TEMPERATURE", "0.5"))
EXTRACTION_TEMPERATURE = float(os.getenv("EXTRACTION_TEMPERATURE", "0.2"))

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


