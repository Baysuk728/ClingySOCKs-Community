# ClingySOCKs Memory Backend

This is the core relational memory engine.

## Installation
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure `.env` (copy from `.env.example`).

## Running the Server
From this directory:
```bash
python -m uvicorn api.main:app --reload --port 8100 --env-file .env
```

## Features
- Relational memory harvesting
- Knowledge graph representation
- MCP integration for external tools
