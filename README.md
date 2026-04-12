<div align="center">

# ClingySOCKs
### Relational memory engine for AI agents

[![Deploy on Railway](https://img.shields.io/badge/Railway-Deploy_on_Railway-9524f2?style=flat&logo=railway&logoColor=white)](https://railway.com/deploy/clingysocks?referralCode=FeqUUU&utm_medium=integration&utm_source=template&utm_campaign=generic)
[![Discord](https://img.shields.io/badge/Discord-Join_Community-7289da?style=flat&logo=discord&logoColor=white)](https://discord.gg/Us7vyUf3)
[![Support the dev](https://img.shields.io/badge/Support_The_Dev-Donate-FFDD00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/clingy.socks)

> **Disclaimer:** ClingySOCKs is an experimental research project exploring persistent memory for AI agents. It is **not** a mental health tool, therapeutic service, or substitute for human relationships. Use responsibly and at your own risk.

</div>

---

## 🚀 One-Click Setup (Recommended)
**No coding or terminal required.** The fastest way to get your own private ClingySOCKs instance running is via Railway.

1. **Click the "Deploy on Railway" button** above.
2. **Enter your OpenRouter API Key** (and your JWT/Encryption secrets if you have them).
3. **Launch!** Your agent will be live and accessible via a private URL in about 60 seconds.

*Note: New Railway users often receive trial credits, which may allow you to run this engine at no cost for your first month.*

---

## 🛠️ Beta Status & Community
ClingySOCKs is currently in **Active Beta**. This means:
* **Things might break:** We are moving fast to improve how AI remembers.
* **Your feedback matters:** If you find a bug or have a feature idea, please let us know!
* **Join the Lab:** Our [Discord Community](https://discord.gg/Us7vyUf3) is where we test new ideas and troubleshoot together.

---

## How It Works
1. **Add your API keys** to `memory/.env` (Gemini, OpenAI, Anthropic, etc.)
2. **Create an agent** — set up a persona with a name, model, and personality.
3. **Import a ChatGPT or Claude export** — feed in your conversation history for memory extraction.
4. **Run harvest** — the engine processes conversations and builds a relational memory graph.
5. **Start chatting** — your agent now remembers context across conversations.

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
