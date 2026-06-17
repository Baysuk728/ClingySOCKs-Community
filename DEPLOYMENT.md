# Deployment Guide — ClingySOCKs

## Prerequisites

- **PostgreSQL 15+** with the [pgvector](https://github.com/pgvector/pgvector) extension
- **Python 3.11+** (backend)
- **Node.js 20+** (frontend)
- At least one LLM API key (Gemini, OpenAI, Anthropic, etc.)

## Repository Structure

```text
/ (Repository Root)
├── docker-compose.yml
├── railway.toml
├── memory/            # Backend (FastAPI)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── api/
│   ├── src/
│   ├── McpServers/
│   └── scripts/
└── frontend/          # Frontend (React + Vite)
    ├── Dockerfile
    ├── nginx.conf
    └── package.json
```

## Option 1: Docker Compose (Recommended)

The easiest way to get everything running:

```bash
# 1. Copy and configure environment
cp memory/.env.example memory/.env
# Edit memory/.env — set DATABASE_URL, API keys, etc.

# 2. Start all services (PostgreSQL + backend + frontend)
docker compose up -d

# 3. Initialize the database
docker exec clingysocks-backend python scripts/setup_db.py --init
```

Services:
- **Backend API**: http://localhost:8100
- **Frontend**: http://localhost:3000
- **PostgreSQL**: localhost:5432

### Environment Variables

See `memory/.env.example` for the full list. At minimum you need:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `GEMINI_API_KEY` or `OPENAI_API_KEY` | At least one LLM API key |
| `MEMORY_API_KEY` | API key for backend auth (leave empty to disable in dev) |
| `JWT_SECRET` | Secret for auth tokens (auto-generated if empty) |
| `ENCRYPTION_KEY` | Key for encrypting stored API keys (64 hex chars) |
| `CORS_ORIGINS` | Frontend URL(s), comma-separated |

For the frontend, set `VITE_MEMORY_API_URL` as a Docker build arg:
```bash
docker compose build --build-arg VITE_MEMORY_API_URL=http://your-backend-url:8100
```

## Option 2: Manual Setup

### Backend

```bash
cd memory
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your values

# Initialize database
python scripts/setup_db.py --init

# Run
python -m uvicorn api.main:app --host 0.0.0.0 --port 8100
```

### Frontend

```bash
cd frontend
npm install

# Set the API URL
export VITE_MEMORY_API_URL=http://localhost:8100

npm run dev     # Development
npm run build   # Production build
```

## Option 3: Railway

1. Connect your GitHub repository to Railway
2. Add a **PostgreSQL** service with pgvector
3. Create two services: **backend** (from `memory/`) and **frontend** (from `frontend/`)
4. Set environment variables on the **backend** service (from `.env.example`)
5. Deploy — Railway uses `railway.toml` automatically

### Railway Environment Variables

On the **backend** service, set:
```
CORS_ORIGINS=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}
VITE_MEMORY_API_URL=https://${{backend.RAILWAY_PUBLIC_DOMAIN}}
```

> **Note**: Replace `frontend` and `backend` with your actual Railway service names.
> The `${{service_name.VARIABLE}}` syntax is Railway's variable reference format.
> The backend auto-detects Railway and allows any `*.up.railway.app` origin as a fallback.

On the **frontend** service, set:
```
VITE_MEMORY_API_URL=https://${{backend.RAILWAY_PUBLIC_DOMAIN}}
```

## Database Setup

The backend requires PostgreSQL with pgvector:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Then initialize tables:
```bash
python scripts/setup_db.py --init
```

To generate embeddings for semantic search (optional):
```bash
python scripts/setup_db.py --embed
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/setup_db.py --init` | Create all database tables |
| `scripts/setup_db.py --embed` | Generate memory embeddings |
| `scripts/run_harvest.py` | Run harvest for ONE agent manually |
| `scripts/run_harvest_all.py` | Run harvest for ALL agents with pending work (for scheduling) |
| `scripts/backup_db.py` | Backup all tables to CSV + SQL |

## Scheduled Harvesting (Railway Cron)

Harvesting can run automatically on a schedule instead of being triggered by
hand. The recommended way is a **separate cron service** in the same Railway
project — a cron service starts on schedule, runs once, and exits, which is
exactly what `scripts/run_harvest_all.py` does (it harvests every agent that has
pending work, then exits). It is more reliable than the in-app background trigger
because nothing recycles it out from under a long backfill, and per-agent
checkpoints make it safe to re-run.

**Set it up (Railway dashboard, ~2 minutes):**

1. Open your project → **New** → **GitHub Repo** → pick this same repo. (Reusing
   the repo means the cron service builds the same image as your API.)
2. Open the new service → **Settings**:
   - **Build**: same as the API — Dockerfile path `memory/Dockerfile`.
   - **Deploy → Custom Start Command**:
     `python scripts/run_harvest_all.py`
   - **Deploy → Cron Schedule**: a 5-field UTC crontab expression, e.g.
     `0 3 * * *` (daily at 03:00 UTC). Minimum frequency is every 5 minutes.
3. **Variables**: give it the same `DATABASE_URL` and provider API key(s) as the
   API service (e.g. `GEMINI_API_KEY` / `OPENAI_API_KEY`). The simplest path is
   to use Railway **shared variables** so both services read the same values.
4. Deploy. Railway runs the start command on the schedule; the script processes
   all due agents and exits (non-zero only if an agent errored).

> The cron service **must exit** when finished or Railway skips the next run —
> `run_harvest_all.py` exits on its own, so no extra handling is needed.

Cost tip: scheduled runs bill an LLM call per pass per chunk. Pick a cheap
harvest model (e.g. `NARRATIVE_MODEL=openai/gpt-4o-mini` or a Gemini Flash/
Flash-Lite model) and optionally set `ECHO_ENABLED=false` / `FACTUAL_ENABLED=false`
to trim calls. See `memory/.env.example` for all harvest cost knobs.
