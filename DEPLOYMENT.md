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
| `scripts/run_harvest.py` | Run harvest pipeline manually |
| `scripts/backup_db.py` | Backup all tables to CSV + SQL |
