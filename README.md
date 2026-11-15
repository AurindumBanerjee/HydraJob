# HydraJob

Self-hosted, personal AI-powered job discovery and application management platform built with FastAPI, PostgreSQL, SQLAlchemy 2.x / Alembic, Ollama, n8n, Streamlit, Docker Compose, and Caddy.

---

## Repository Structure

```text
HydraJob/
├── backend/                     # FastAPI REST API, SQLAlchemy 2.x, Alembic, domain engines, pytest
│   ├── app/
│   │   ├── api/routes/          # REST endpoints (/health, /system, /profile, /companies, /jobs, /applications, /tasks, /searches)
│   │   ├── core/                # Settings, JSON logging with secret masking, X-API-Key security, exceptions
│   │   ├── db/models/           # 13 SQLAlchemy 2.x ORM models
│   │   ├── db/repositories/     # Transactional repository layer
│   │   ├── schemas/             # Pydantic v2 request/response contracts
│   │   └── services/            # Domain engines (llm, scraping, matching, email, system_status)
│   ├── alembic/                 # Database migrations (baseline + Phase 1-8 schema)
│   ├── tests/                   # Unit & integration tests + offline HTML/JSON fixtures
│   ├── alembic.ini
│   ├── Dockerfile
│   └── pyproject.toml
├── dashboard/                   # Streamlit multipage UI (calls FastAPI only, warm-paper theme)
│   ├── components/              # Theme CSS, status badges, modular views
│   ├── pages/                   # 01_Jobs .. 10_System_Health
│   ├── services/                # HydraJobApiClient (HTTPX) & Asia/Kolkata time helpers
│   ├── tests/                   # Mocked HTTPX client & Streamlit AppTest suite
│   ├── app.py
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── requirements.txt
├── config/
│   ├── company_sources.yaml     # 19 seed company career-page entries (Technology, AI, Quant)
│   └── job_searches.yaml        # 4 initial search configurations (ML/AI, Data Science, SWE, Internships)
├── data/
│   └── samples/                 # Non-sensitive sample payloads
├── docs/
│   ├── architecture.md          # Service topology, pipeline, and engineering rules
│   ├── database_schema.md       # All 13 tables, 16 application statuses, 18 email classes, dedup rules
│   ├── deployment_aws.md        # EC2, EBS, Caddy HTTPS, n8n hardening, log rotation, backups, AWS Budgets
│   ├── setup.md                 # Local development setup & verification
│   └── ui_style_guide.md        # Warm-paper editorial UI & SVG diagram conventions
├── figures/
│   ├── system_topology.svg              # Browser -> Caddy -> Streamlit/n8n -> FastAPI -> Postgres/Ollama
│   ├── data_model_er.svg                # 13-table ER diagram
│   └── ingestion_evaluation_pipeline.svg# SSRF -> Extraction -> Dedup -> Eligibility/Scoring -> Tasks
├── n8n/
│   ├── workflows/               # 4 credential-free n8n workflow JSON templates
│   └── README.md                # n8n import & credential configuration guide
├── supporting_codes/
│   ├── postgres-init/
│   │   └── 01-init-databases.sh # Creates hydrajob_test & n8n DBs on first boot
│   ├── generate_secrets.py      # Generates strong secrets for .env
│   ├── seed_initial_data.py     # Validates & seeds config/*.yaml into FastAPI
│   ├── verify_compose.py        # Validates dev & prod Docker Compose configs
│   └── verify_n8n_workflows.py  # Validates n8n JSON structure & secret hygiene
├── to_delete/                   # Staging folder for deprecated/superseded files
├── Caddyfile                    # Production HTTPS reverse proxy & Basic Auth config
├── docker-compose.yml           # Base stack (postgres, ollama, backend, dashboard, n8n, caddy)
├── docker-compose.dev.yml       # Local hot-reload override
├── docker-compose.prod.yml      # Production override (removes internal host ports)
├── .env.example                 # Environment variable template & secret instructions
└── .gitignore
```

---

## Architecture Diagrams

- **System Topology:** [figures/system_topology.svg](figures/system_topology.svg)
- **Data Model (13 Tables):** [figures/data_model_er.svg](figures/data_model_er.svg)
- **Ingestion & Evaluation Pipeline:** [figures/ingestion_evaluation_pipeline.svg](figures/ingestion_evaluation_pipeline.svg)

---

## Quick Start (Local Development)

1. **Create `.env` from template and generate secrets:**
   ```bash
   cp .env.example .env
   python supporting_codes/generate_secrets.py
   ```
   Update `APP_SECRET_KEY`, `APP_API_KEY`, `POSTGRES_PASSWORD`, `N8N_ENCRYPTION_KEY`, and `DATABASE_URL` in `.env`. Never commit `.env`.

2. **Validate Docker Compose & n8n templates:**
   ```bash
   python supporting_codes/verify_compose.py
   python supporting_codes/verify_n8n_workflows.py
   python supporting_codes/seed_initial_data.py
   ```

3. **Start the stack:**
   ```bash
   docker compose up --build -d
   ```
   Or with hot reload for backend/dashboard development:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
   ```

4. **Pull an Ollama model explicitly** (models are never auto-pulled on container startup):
   ```bash
   docker compose exec ollama ollama pull qwen2.5:7b-instruct
   docker compose exec ollama ollama list
   ```

5. **Run Alembic migrations and seed initial registry/searches:**
   ```bash
   docker compose exec backend alembic upgrade head
   python supporting_codes/seed_initial_data.py --apply --api-base-url http://127.0.0.1:8000 --api-key "<APP_API_KEY>"
   ```

6. **Local service endpoints** (all bound strictly to `127.0.0.1` in dev):
   - FastAPI Health: `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/health/ready`
   - FastAPI Docs (Swagger): `http://127.0.0.1:8000/docs`
   - Streamlit Dashboard: `http://127.0.0.1:8501`
   - n8n UI: `http://127.0.0.1:5678`
   - Ollama: private Docker network only (`http://ollama:11434`, port `11434` is never published to host)

---

## Phase 0–8 Usage Guide

- **Phase 0 (Foundation & Health):** Verify PostgreSQL and Ollama reachability on Dashboard **System Health** or `GET /api/v1/system/status`.
- **Phase 1 (Manual CRUD & Profile):** Edit candidate profile (`GET/PUT /api/v1/profile`), manage multiple resume versions (`/api/v1/resumes`), track companies (`/api/v1/companies`), jobs (`/api/v1/jobs`), applications (`/api/v1/applications`), and tasks (`/api/v1/tasks`).
- **Phase 2 (Job URL Intake):** Submit job URLs for SSRF-checked retrieval, JSON-LD/OpenGraph/HTML/Playwright/Ollama structured extraction, manual field correction, and deduplication.
- **Phase 3 (Eligibility & Scoring):** Evaluate mandatory eligibility (`ELIGIBLE | UNCERTAIN | INELIGIBLE | NOT_EVALUATED`), weighted score `0.30E + 0.30T + 0.20P + 0.10R + 0.10L`, recommended resume, and policy-gated internal tasks.
- **Phase 4 (Career-Page Registry):** Inspect, test, and selectively activate the 19 seeded company sources in `config/company_sources.yaml` (unverified/JS portals default to `active: false` / `NEEDS_CONFIGURATION`).
- **Phase 5 (Discovery & Searches):** Run saved search configurations (`config/job_searches.yaml`) and incremental scans across active sources.
- **Phase 6 (Streamlit Dashboard):** Operate all workflows across the multipage Streamlit UI (strictly via FastAPI, `Asia/Kolkata` display timezone).
- **Phase 7 (n8n & AWS Production):** Import workflows from `n8n/workflows/` per [n8n/README.md](n8n/README.md), and deploy on AWS EC2 with `docker-compose.prod.yml` + `Caddyfile` per [docs/deployment_aws.md](docs/deployment_aws.md).
- **Phase 8 (Recruitment Email Intelligence):** Read-only Gmail / synthetic email classification across 18 categories, confidence-gated status transitions (`>= 0.90` auto, `0.70–0.89` review queue, `< 0.70` no auto-update), and immutable `ApplicationEvent` logging.

---

## REST API Reference & Example Requests

All `/api/v1/*` routes expect header `X-API-Key: <APP_API_KEY>` when `APP_API_KEY` is configured (`/health` and `/health/ready` remain open). Paginated list endpoints return `{"items": [...], "total": int, "limit": int, "offset": int}`.

### Implemented Endpoints (Phase 0–8)

| Area | Endpoints |
| :--- | :--- |
| **Health & System** | `GET /health`, `GET /health/ready`, `GET /api/v1/system/status` |
| **Profile & Resumes** | `GET /api/v1/profile`, `PUT /api/v1/profile`, `GET/POST /api/v1/resumes`, `GET/PUT/DELETE /api/v1/resumes/{id}` |
| **Companies & Sources** | `GET/POST /api/v1/companies`, `GET/PUT/DELETE /api/v1/companies/{id}`, `GET/POST /api/v1/sources`, `GET/PUT/DELETE /api/v1/sources/{id}` |
| **Source Onboarding** | `POST /api/v1/sources/register`, `POST /api/v1/sources/{id}/test`, `POST /api/v1/sources/{id}/activate`, `POST /api/v1/sources/{id}/deactivate`, `GET /api/v1/sources/{id}/jobs`, `GET /api/v1/sources/{id}/scans` |
| **Jobs, Ingest & Match** | `GET/POST /api/v1/jobs`, `GET/PUT/DELETE /api/v1/jobs/{id}`, `POST /api/v1/jobs/ingest`, `GET /api/v1/jobs/ingest/{run_id}`, `POST /api/v1/jobs/ingest/{run_id}/reprocess`, `POST /api/v1/jobs/{id}/evaluate`, `GET /api/v1/jobs/{id}/evaluations` |
| **Applications & Events** | `GET/POST /api/v1/applications`, `GET/PUT/DELETE /api/v1/applications/{id}`, `PATCH /api/v1/applications/{id}/status`, `GET /api/v1/applications/{id}/events` |
| **Tasks** | `GET/POST /api/v1/tasks`, `GET/PUT/DELETE /api/v1/tasks/{id}`, `PATCH /api/v1/tasks/{id}/status` |
| **Searches & Discovery** | `GET/POST /api/v1/searches`, `GET/PUT/DELETE /api/v1/searches/{id}`, `POST /api/v1/discovery/scan-all`, `POST /api/v1/discovery/scan-source/{id}`, `POST /api/v1/discovery/run-search/{id}`, `GET /api/v1/discovery/runs`, `GET /api/v1/discovery/runs/{id}`, `POST /api/v1/discovery/runs/{id}/retry`, `GET /api/v1/discovery/new-jobs`, `GET /api/v1/discovery/failed-sources` |
| **Recruitment Emails** | `GET /api/v1/emails`, `POST /api/v1/emails/ingest-synthetic`, `POST /api/v1/emails/sync`, `POST /api/v1/emails/{id}/review` |

### Example Requests

```bash
export API="http://127.0.0.1:8000"
export KEY="your-app-api-key"

# 1. Check readiness and system status
curl -fsS "$API/health/ready"
curl -fsS -H "X-API-Key: $KEY" "$API/api/v1/system/status"

# 2. Fetch auto-seeded user profile
curl -fsS -H "X-API-Key: $KEY" "$API/api/v1/profile"

# 3. Create a company and a job manually
curl -fsS -X POST "$API/api/v1/companies" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"name":"Example AI","website":"https://example.ai","industry":"AI"}'

curl -fsS -X POST "$API/api/v1/jobs" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"company_id":"<COMPANY_UUID>","title":"ML Engineer","location":"Bengaluru","required_skills":["Python","PyTorch"]}'

# 4. Create an application and advance status (records immutable ApplicationEvent)
curl -fsS -X POST "$API/api/v1/applications" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"job_id":"<JOB_UUID>","status":"TO_APPLY","priority":"HIGH"}'

curl -fsS -X PATCH "$API/api/v1/applications/<APP_UUID>/status" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"status":"APPLIED","notes":"Submitted via company portal"}'
```

---

## Backup & Restore

```bash
# Backup application and n8n PostgreSQL databases
mkdir -p backups
docker compose exec -T postgres pg_dump -U hydrajob -Fc hydrajob > backups/hydrajob.dump
docker compose exec -T postgres pg_dump -U hydrajob -Fc n8n > backups/n8n.dump

# Restore
docker compose exec -T postgres pg_restore -U hydrajob --clean --if-exists -d hydrajob < backups/hydrajob.dump
docker compose exec -T postgres pg_restore -U hydrajob --clean --if-exists -d n8n < backups/n8n.dump
```

See [docs/deployment_aws.md](docs/deployment_aws.md) for automated AWS EBS snapshots and secret backup guidance.

---

## AWS EC2 & EBS Sizing Summary

| Component | Recommendation | Notes |
| :--- | :--- | :--- |
| **EC2 Instance** | `t3a.xlarge` or `m6i.xlarge` (4 vCPU, 16 GB RAM) | Minimum realistic baseline for a quantized 7B–8B Ollama model + full stack; use `m6i.2xlarge` (32 GB) or `g5.xlarge` GPU for larger models or faster inference |
| **EBS Volume** | 60–100 GB `gp3` (encrypted) | Covers OS, Docker images, PostgreSQL + WAL, n8n state, rotated logs, backups, and Ollama model weights |
| **Ingress** | Caddy on ports `80` / `443` only | `docker-compose.prod.yml` removes all internal host ports; use AWS SSM Session Manager instead of open SSH |
| **Cost Control** | AWS Budgets alerts at 50% / 80% / 100% | Monitor EC2, EBS, and data transfer independently of promotional credits |

Full documentation: [docs/setup.md](docs/setup.md) | [docs/architecture.md](docs/architecture.md) | [docs/database_schema.md](docs/database_schema.md) | [docs/deployment_aws.md](docs/deployment_aws.md) | [docs/ui_style_guide.md](docs/ui_style_guide.md) | [n8n/README.md](n8n/README.md).
