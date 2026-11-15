# HydraJob Local Setup Guide

## Prerequisites

- Docker Engine & Docker Compose v2+
- Python 3.11+ (for local secret generation, helper scripts, and running tests outside containers)
- Git

## 1. Configure Environment Variables

Copy `.env.example` to `.env` (never commit `.env`):

```bash
cp .env.example .env
```

Generate cryptographically strong secrets and update `.env`:

```bash
python supporting_codes/generate_secrets.py
```

Copy the generated values into `.env` for:
- `APP_SECRET_KEY`
- `APP_API_KEY`
- `POSTGRES_PASSWORD`
- `N8N_ENCRYPTION_KEY`

Also update `DATABASE_URL` in `.env` so its password matches `POSTGRES_PASSWORD`:

```env
DATABASE_URL=postgresql+psycopg://hydrajob:<POSTGRES_PASSWORD>@postgres:5432/hydrajob
```

## 2. Validate Docker Compose Configuration

Before starting containers, verify the Compose files against `.env`:

```bash
docker compose --env-file .env config
python supporting_codes/verify_compose.py
```

## 3. Start Services Locally

Standard local startup (binds `postgres`, `backend`, `dashboard`, and `n8n` strictly to `127.0.0.1`):

```bash
docker compose up --build -d
```

Development hot-reload mode (mounts `./backend/app`, `./backend/alembic`, and `./dashboard`):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Check container status and health checks:

```bash
docker compose ps
```

## 4. Pull an Ollama Model Explicitly

Ollama does **not** automatically pull large models on startup. Pull your configured model explicitly once the `ollama` container is running:

```bash
docker compose exec ollama ollama pull qwen2.5:7b-instruct
docker compose exec ollama ollama list
```

If using a different model, update `OLLAMA_MODEL` in `.env` and restart `backend`:

```bash
docker compose up -d backend
```

## 5. Run Alembic Migrations

Apply the baseline database schema migration inside the `backend` container:

```bash
docker compose exec backend alembic upgrade head
```

## 6. Verify Endpoints & UI

- FastAPI liveness: `curl http://127.0.0.1:8000/health`
- FastAPI readiness (checks PostgreSQL): `curl http://127.0.0.1:8000/health/ready`
- FastAPI system status (include `X-API-Key` if `APP_API_KEY` is set):
  ```bash
  curl -H "X-API-Key: <your-app-api-key>" http://127.0.0.1:8000/api/v1/system/status
  ```
- Streamlit Dashboard: `http://127.0.0.1:8501`
- n8n Orchestrator: `http://127.0.0.1:5678`

## 7. Running Tests Locally

Backend tests:

```bash
cd backend
python -m pytest
```

Dashboard tests:

```bash
cd dashboard
python -m pytest
```

## 8. Stopping and Resetting

Stop containers while preserving volumes:

```bash
docker compose down
```

Remove containers and persistent volumes (destructive — deletes DBs, n8n workflows, and pulled Ollama models):

```bash
docker compose down -v
```
