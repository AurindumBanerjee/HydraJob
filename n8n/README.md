# HydraJob n8n Orchestration

n8n serves as the **workflow orchestrator** for HydraJob: scheduling triggers, bounded retries, and calling FastAPI REST endpoints.

## Architectural Rules

1. **n8n coordinates; Python implements business logic.** Do not embed scraping, matching, or SQL inside n8n Code nodes; call FastAPI endpoints instead.
2. **PostgreSQL is the single source of truth.** n8n uses its own `n8n` database inside the `postgres` container (`DB_TYPE=postgresdb`), isolated from the `hydrajob` application database.
3. **Never export credentials or secrets.** All workflow files in `n8n/workflows/` use an `httpHeaderAuth` credential placeholder (`HydraJob X-API-Key`) and `$env.HYDRAJOB_API_BASE_URL` (falling back to `http://backend:8000`).
4. **Timezone:** `GENERIC_TIMEZONE=Asia/Kolkata` and `TZ=Asia/Kolkata` are set in `docker-compose.yml` and every workflow's `settings.timezone`.
5. **Encryption key:** Keep `N8N_ENCRYPTION_KEY` backed up securely; losing it renders stored n8n credentials unreadable.

---

## Included Workflows (`n8n/workflows/`)

| Workflow File | Trigger | Target FastAPI Endpoints | Purpose |
| :--- | :--- | :--- | :--- |
| `01_manual_job_intake.json` | `POST /webhook/hydrajob/job-intake` | `POST /api/v1/jobs/ingest` -> `GET /api/v1/jobs/ingest/{id}` -> `POST /api/v1/jobs/{id}/evaluate` | Ingest a submitted URL, wait/poll for extraction, and run Ollama + eligibility evaluation |
| `02_scheduled_company_scans.json` | Schedule (every 6 hours) | `GET /api/v1/sources?is_active=true` -> `POST /api/v1/discovery/scan-source/{id}` | Sequentially scan active company sources with `continueOnFail: true` so one failure never blocks the rest |
| `03_search_execution.json` | Daily 09:00 IST / Webhook `/webhook/hydrajob/run-search` | `GET /api/v1/searches?is_active=true` -> `POST /api/v1/discovery/run-search/{id}` | Execute active search profiles and trigger downstream evaluation/task creation |
| `04_retry_and_failure_handling.json` | Schedule (every 2 hours) | `GET /api/v1/discovery/failed-sources` -> `POST /api/v1/discovery/scan-source/{id}` | Retry failed sources within bounded limit (`consecutive_failures < 3`); escalate persistent failures to the dashboard |

---

## Setup & Import Instructions

1. **Optional n8n environment variable:** In `docker-compose.yml`, `n8n` can read `HYDRAJOB_API_BASE_URL` (defaults to `http://backend:8000` inside workflow expressions). If n8n blocks `$env` access in expressions on newer images, set `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` in `.env` or edit the URL expressions directly to `http://backend:8000`.
2. **Create the `HydraJob X-API-Key` credential in n8n UI:**
   - Open n8n (`http://127.0.0.1:5678` locally or `https://<domain>/n8n/` in production).
   - Go to **Credentials -> Add Credential -> Header Auth**.
   - Name: `HydraJob X-API-Key`
   - Header Name: `X-API-Key`
   - Header Value: `<your APP_API_KEY from .env>`
3. **Import workflows:**
   - Go to **Workflows -> Import from File** and import each JSON file in `n8n/workflows/`.
   - Open each HTTP Request node and select your newly created `HydraJob X-API-Key` credential.
   - Verify with a manual execution before toggling each workflow **Active**.
4. **Validate workflow JSONs before committing:**
   ```bash
   python supporting_codes/verify_n8n_workflows.py
   ```
   Always scrub credential IDs/secrets before exporting updated workflows back to `n8n/workflows/`.
