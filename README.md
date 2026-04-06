# ClingySOCKs

Relational memory engine for AI agents.

> **Disclaimer:** ClingySOCKs is an experimental research project exploring persistent memory for AI agents. It is **not** a mental health tool, therapeutic service, or substitute for human relationships. Use responsibly and at your own risk.

## How It Works

1. **Add your API keys** to `memory/.env` (Gemini, OpenAI, Anthropic, etc.)
2. **Create an agent** — set up a persona with a name, model, and personality
3. **Import a ChatGPT export** — feed in your conversation history for memory extraction
4. **Run harvest** — the engine processes conversations and builds a relational memory graph
5. **Start chatting** — your agent now remembers context across conversations

## Quick Start

### Backend (Memory Server)
```bash
cd memory
cp .env.example .env
# Edit .env — set DATABASE_URL and at least one LLM API key
python -m uvicorn api.main:app --reload --port 8100
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Docker (Full Stack)
```bash
cp memory/.env.example memory/.env
# Edit memory/.env
docker compose up -d
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for full deployment instructions.

## Local Models (Ollama / LM Studio)

ClingySOCKs supports local LLM inference via Ollama or any OpenAI-compatible server.

1. Install and start [Ollama](https://ollama.com) (or [LM Studio](https://lmstudio.ai)):
   ```bash
   ollama serve
   ollama pull llama3.1
   ```

2. Add to `memory/.env`:
   ```env
   # Ollama (default port)
   OLLAMA_API_BASE=http://localhost:11434

   # Or OpenAI-compatible server (LM Studio, vLLM, llama.cpp)
   # LOCAL_API_BASE=http://localhost:1234
   ```

3. Restart the backend — "Local (Ollama / LM Studio)" will appear as a provider in the persona editor with your downloaded models auto-discovered.

## Production Security

In development, fallback secrets are used automatically. For production, set these in `memory/.env`:

```env
ENCRYPTION_KEY=<random-64-hex-chars>    # openssl rand -hex 32
JWT_SECRET=<random-64-hex-chars>        # openssl rand -hex 32
REQUIRE_SECRETS=true                     # refuse to start without the above
```

## Project Structure
- `memory/`: Backend Python application (FastAPI, SQLAlchemy, PostgreSQL + pgvector)
- `frontend/`: React + Vite frontend
- `memory/McpServers/`: MCP servers for agent tool access
