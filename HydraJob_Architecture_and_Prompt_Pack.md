# HydraJob --- Architecture, Hosting Plan & Coding Prompt Pack

**Version:** 2.0\
**Deployment direction:** AWS-hosted, self-managed\
**LLM inference:** Ollama (no ChatGPT/OpenAI API dependency)\
**Primary focus:** Manual job/company management, job-link ingestion,
company career-page discovery and job matching\
**Deferred:** Gmail synchronization and recruitment-email intelligence

------------------------------------------------------------------------

# 1. Product direction

HydraJob is a personal job-discovery and application-management
platform. It should:

1.  Let the user manually add, edit, archive and manage companies,
    career pages, jobs and applications.
2.  Accept individual job URLs and extract structured job information.
3.  Maintain a registry of company career pages that the user can add or
    remove without changing application code.
4.  Periodically scan active company sources and discover new openings.
5.  Evaluate jobs against the user's configurable profile and resume
    versions.
6.  Deduplicate the same opening discovered through multiple sources.
7.  Create internal application tasks and maintain an application
    history.
8.  Provide a Streamlit dashboard for all operations.
9.  Eventually monitor Gmail for recruitment events. This is an endgame
    phase and must not delay the initial product.

## Explicit scope priorities

**Build first:** - Manual CRUD for companies, sources, jobs, profiles,
resumes, applications and tasks. - Job URL submission and extraction. -
Company career-page registration and testing. - Career-page scanning and
scheduled discovery. - Ollama-based extraction and matching. - Streamlit
dashboard. - n8n orchestration.

**Build later:** - Gmail OAuth and inbox synchronization. - Recruitment
email classification. - Automatic application-status updates from
emails. - Email-driven reminders and follow-ups.

Do not implement Gmail monitoring in the early phases. Do not request
Gmail credentials or OAuth scopes until the dedicated email phase.

------------------------------------------------------------------------

# 2. Hosting and infrastructure decisions

## 2.1 Primary hosting: AWS

Use the user's existing AWS account and available credits as the primary
hosting environment.

Recommended initial deployment:

-   **Amazon EC2:** Runs Docker Compose and the HydraJob services.
-   **Amazon EBS gp3:** Persistent storage for PostgreSQL and
    application data.
-   **Elastic IP or stable DNS:** Stable endpoint for the application
    and n8n.
-   **Security Groups:** Restrict inbound access.
-   **AWS Budgets:** Cost monitoring and alerts.
-   **AWS Systems Manager Session Manager:** Prefer this for server
    administration where practical; avoid exposing SSH broadly.
-   **Backups:** Automated PostgreSQL backups and periodic EBS
    snapshots.

Do not assume promotional credits cover every AWS service. Check credit
eligibility and expiration in the user's AWS Billing console before
choosing paid resources.

Start with one EC2 instance for simplicity, but keep services
containerized and separable. The architecture should permit moving
Ollama to a separate GPU instance later without changing the backend's
business logic.

## 2.2 Ollama deployment interpretation

"Ollama local models" means models run locally on the AWS EC2 host or on
a private inference host controlled by the user. It does **not** mean
calling the ChatGPT API.

-   Run Ollama as a Docker service or managed host process.
-   Keep its API private to the Docker network or private VPC.
-   Do not expose port 11434 publicly.
-   Configure model names through environment variables.
-   Use structured outputs / JSON mode where supported by the selected
    model.
-   Validate every model response with Pydantic.
-   Provide deterministic fallback and manual review when extraction is
    malformed or confidence is low.

A small EC2 instance is not automatically suitable for Ollama. Choose
RAM and compute after selecting the intended model and quantization. As
a planning guide, a quantized 7B model commonly needs several GB of
memory for weights plus additional memory for context and runtime; a 16
GB RAM machine is a more realistic starting point than a tiny free-tier
VM, while larger models may need 32 GB or a GPU. Benchmark the actual
workload before committing to a larger instance.

Do not claim that an Ollama deployment is free merely because Ollama
software is open source: EC2 compute, storage and data transfer can
still incur charges.

## 2.3 Initial service topology

``` text
User Browser
    |
    +---- HTTPS / Reverse Proxy
               |
               +---- Streamlit Dashboard
               |
               +---- FastAPI Backend
                         |
                         +---- PostgreSQL
                         |
                         +---- Ollama (private network)
                         |
                         +---- Job Source Adapters

n8n
    |
    +---- FastAPI internal endpoints
    +---- Scheduled career-page scans
    +---- Job ingestion and evaluation triggers

Gmail integration: NOT CONNECTED IN EARLY PHASES
```

## 2.4 Hosting alternatives

Use AWS EC2 as primary because the user already has AWS credits and
needs persistent 24/7 processes.

Potential alternatives: - Oracle Cloud Always Free: possible low-cost
fallback for lightweight services, subject to capacity and idle-instance
reclamation. Do not assume it can run a useful Ollama model. - Render
free services: unsuitable for persistent 24/7 workers because free web
services sleep and free database persistence is time-limited. - Fly.io:
technically capable but not a guaranteed free always-on option. - AWS
Lightsail: simpler VPS alternative, but EC2 offers more flexibility for
Ollama and future scaling.

Do not distribute the system across several providers just to chase free
tiers. That increases operational complexity.

------------------------------------------------------------------------

# 3. Final technology stack

  -----------------------------------------------------------------------
  Layer                   Technology              Responsibility
  ----------------------- ----------------------- -----------------------
  Orchestration           Self-hosted n8n         Scheduling, triggers,
                                                  retries and workflow
                                                  coordination

  Backend                 Python + FastAPI        Business logic and REST
                                                  API

  Database                PostgreSQL              Single source of truth

  ORM                     SQLAlchemy 2.x          Database access

  Migrations              Alembic                 Schema evolution

  Validation              Pydantic                API and LLM output
                                                  validation

  Scraping                HTTPX, BeautifulSoup,   Job-page retrieval and
                          Playwright              parsing

  Local AI                Ollama                  Extraction, matching
                                                  and classification

  Dashboard               Streamlit               Manual management and
                                                  monitoring

  Deployment              Docker Compose          Reproducible service
                                                  deployment

  Reverse proxy           Caddy or Nginx          HTTPS and routing

  Tests                   pytest                  Automated verification
  -----------------------------------------------------------------------

Do not introduce LangGraph, vector databases, Redis or a hosted LLM API
in the initial implementation unless a demonstrated requirement
justifies it.

PostgreSQL is the source of truth. n8n is an orchestrator, not a second
business-logic backend. Streamlit should call FastAPI rather than access
PostgreSQL directly.

------------------------------------------------------------------------

# 4. Repository target structure

``` text
HydraJob/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   └── dependencies.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── logging.py
│   │   ├── db/
│   │   │   ├── models/
│   │   │   ├── repositories/
│   │   │   └── session.py
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── jobs/
│   │   │   ├── scraping/
│   │   │   ├── matching/
│   │   │   ├── companies/
│   │   │   └── tasks/
│   │   └── main.py
│   ├── tests/
│   ├── alembic/
│   └── pyproject.toml
├── dashboard/
│   ├── pages/
│   ├── components/
│   ├── services/
│   └── app.py
├── n8n/
│   ├── workflows/
│   └── README.md
├── config/
│   ├── company_sources.yaml
│   └── job_searches.yaml
├── data/
│   └── samples/
├── docs/
│   ├── architecture.md
│   ├── database_schema.md
│   ├── deployment_aws.md
│   └── setup.md
├── scripts/
├── tests/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .gitignore
├── README.md
└── pyproject.toml
```

The coding agent may refine the structure, but must preserve clear
separation between API routes, business services, persistence, dashboard
and orchestration.

------------------------------------------------------------------------

# 5. Master instructions for the coding agent

## PROMPT 00 --- HydraJob master engineering instructions

You are the lead software architect and senior full-stack engineer
building HydraJob in the existing GitHub repository.

### Product objective

Build a personal AI-powered job discovery and application management
platform. The user must be able to manually manage company records,
career-page sources, jobs, profile information, resume versions,
application records and tasks. The system must also accept job URLs,
extract job details, discover openings from registered career pages and
evaluate jobs against the user's profile.

Gmail synchronization is explicitly deferred to the final phase. Do not
implement Gmail access, OAuth or email monitoring before that phase.

### Fixed technology choices

-   Python and FastAPI backend.
-   PostgreSQL database.
-   SQLAlchemy 2.x and Alembic.
-   Pydantic validation.
-   Self-hosted n8n.
-   Ollama for all LLM inference.
-   HTTPX, BeautifulSoup and Playwright for permitted page retrieval and
    extraction.
-   Streamlit dashboard.
-   Docker Compose.
-   pytest.

Do not use the ChatGPT API or OpenAI API for inference. Do not add a
hosted LLM provider as a fallback. Ollama must be configurable by base
URL and model name.

### User profile context

Use configurable profile records, not hardcoded personal details.
Initial profile context supplied by the user includes:

-   B.Tech Computer Science and Engineering student at IIT Jodhpur.
-   Expected graduation year: 2027.
-   Data Science internship experience at InfoEdge.
-   Python, C++, SQL, PyTorch and machine learning.
-   NLP, LLMs, RAG, computer vision and model fine-tuning.
-   Projects including Script-Identifier, TinyML, ANN in C, Smart
    Surveillance and company-knowledge model research.

Treat this as initial seed information that the user can edit. Do not
assume every role is eligible.

### Engineering rules

1.  PostgreSQL is the single source of truth.
2.  n8n coordinates workflows; Python implements business logic.
3.  Streamlit communicates with FastAPI, not directly with PostgreSQL.
4.  Ollama is accessed through a dedicated LLM service abstraction.
5.  Validate every LLM response with Pydantic.
6.  Unknown information must remain unknown; never fabricate job
    requirements, deadlines or eligibility.
7.  Keep source adapters modular and dynamically configurable.
8.  Make ingestion, evaluation and task creation idempotent.
9.  Preserve application-event history.
10. Use timezone-aware timestamps and store them in UTC.
11. Use Asia/Kolkata for user-facing time display.
12. Add tests and documentation for every phase.
13. Use Alembic for all schema changes.
14. Never commit credentials, tokens, private resumes or personal data.
15. Respect website terms, robots.txt and rate limits. Do not bypass
    login, CAPTCHA, paywalls or access controls.
16. Prevent SSRF: block localhost, private IPs, link-local addresses and
    unsafe redirects in user-submitted URLs.
17. Do not expose Ollama, PostgreSQL or internal service ports publicly.
18. Do not automatically submit job applications.

### AWS deployment rules

The target runtime is AWS EC2 using Docker Compose and persistent EBS
storage. Keep local development possible with the same Compose setup.

-   Use environment variables for secrets.
-   Keep persistent volumes for PostgreSQL and n8n.
-   Add health checks.
-   Document backups and restore.
-   Configure a reverse proxy and HTTPS for public access.
-   Do not expose PostgreSQL or Ollama to the internet.
-   Include cost-awareness and instance-sizing documentation.
-   Do not assume promotional AWS credits cover all services.

### Required phase workflow

For each phase: 1. Inspect the current repository. 2. Read existing docs
and tests. 3. Implement only the requested phase. 4. Do not overwrite
working code unnecessarily. 5. Add unit and integration tests. 6. Run
tests and report actual results. 7. Update documentation and
`.env.example`. 8. Provide a concise list of changed files. 9. List
limitations and unresolved issues. 10. Stop and wait for approval before
beginning the next phase.

Never claim functionality is complete if it is only scaffolded.

------------------------------------------------------------------------

# 6. Ordered implementation prompts

Execute these prompts one at a time. Complete and verify a phase before
starting the next.

## PROMPT 01 --- Phase 0: AWS-ready project foundation

Read PROMPT 00 and inspect the repository.

Establish the foundational HydraJob project and a reproducible Docker
Compose development environment.

### A. Services

Configure these services:

**PostgreSQL** - Use a stable supported PostgreSQL image. - Persistent
named volume. - Credentials from environment variables. - Health
check. - No public port exposure in production. - Separate application
and test databases.

**n8n** - Official n8n image. - Persistent data volume. - Encryption key
from environment. - Prefer PostgreSQL-backed persistence using a
separate database/schema or database as supported by n8n
configuration. - Set timezone to Asia/Kolkata. - Do not hardcode
credentials in workflow exports.

**FastAPI** - Python backend. - Port 8000 internally. - Development
reload profile. - Production-compatible image. - Health and readiness
endpoints.

**Streamlit** - Port 8501 internally. - Connect only to FastAPI.

**Ollama** - Official Ollama image or a documented host installation. -
Persistent model volume. - Private Docker-network access only. -
Configurable model name. - Health check. - Do not download a large model
automatically during every container start. - Document how to pull and
verify a model explicitly.

**Reverse proxy** - Add Caddy or Nginx for production HTTPS. - Do not
expose internal service ports through the reverse proxy unless required.

### B. Backend foundation

Implement: - FastAPI application initialization. - Pydantic Settings. -
SQLAlchemy engine and session. - Alembic. - Structured logging. - Common
exception handling. - `GET /health`. - `GET /health/ready`. -
`GET /api/v1/system/status`, returning service availability without
revealing secrets.

### C. Environment configuration

Create `.env.example` with placeholders for:

``` env
APP_ENV=development
APP_SECRET_KEY=

POSTGRES_DB=hydrajob
POSTGRES_USER=hydrajob
POSTGRES_PASSWORD=
DATABASE_URL=

N8N_ENCRYPTION_KEY=
N8N_HOST=
N8N_PROTOCOL=http
N8N_PORT=5678

OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=

API_BASE_URL=http://localhost:8000
DASHBOARD_URL=http://localhost:8501
```

Include secure secret-generation instructions. Do not commit a real
`.env`.

### D. AWS documentation

Create `docs/deployment_aws.md` covering: - EC2 prerequisites. - EBS
volume planning. - Security groups. - Docker installation. - Compose
deployment. - Persistent storage. - Reverse proxy and HTTPS. -
Backups. - Updating and rollback. - AWS budget alerts. - Ollama RAM and
model-size considerations.

Do not provision AWS resources or claim a deployment succeeded unless
you actually have authorized AWS access and performed it.

### E. Tests

Verify: - Docker configuration validity. - PostgreSQL readiness. - API
health. - Database connectivity. - Ollama connectivity. - Streamlit
startup. - n8n startup. - Alembic migration execution.

Do not implement job scraping or Gmail integration yet.

Deliver a repository tree, startup instructions, service health report
and test results.

------------------------------------------------------------------------

## PROMPT 02 --- Phase 1: Core database, manual CRUD and profile management

Read all previous documentation and inspect Phase 0.

Implement the core data model and REST APIs. The immediate objective is
to let the user manage all important records manually without requiring
scraping or AI.

### A. Database models

Implement:

**UserProfile** - Name, email, education, degree, branch, university,
graduation year, CGPA. - Experience summary. - Skills. - Preferred
roles. - Preferred locations. - Excluded locations. - Created and
updated timestamps.

**Resume** - Name, file path, file type, extracted text, skills, active
flag, timestamps. - Support multiple resume versions. - Never expose
resume files publicly.

**Company** - Name, website, industry, description, notes, timestamps.

**CompanySource** - Company ID, source name, career URL, source type,
extraction method, JSON configuration, active status, last checked, last
successful scan, last error.

**Job** - Company ID, title, description, location, country, employment
type, workplace type, experience requirement, graduation-year
requirement, degree requirement, required skills, preferred skills,
responsibilities, salary, currency, application deadline, application
URL, canonical URL, source metadata, raw extraction data, active status
and timestamps.

**JobSourceReference** - Job ID, source ID, source external ID, original
URL, first seen, last seen. - Preserve multiple source references for
one deduplicated job.

**JobEvaluation** - Job ID, profile version/reference, eligibility,
overall score, component scores, matched skills, missing skills,
strengths, concerns, model name, evaluation version and timestamp.

**JobApplication** - Job ID, selected resume ID, status, priority, match
score, eligibility, application date, notes, created and updated
timestamps.

**ApplicationEvent** - Application ID, event type, previous status, new
status, timestamp, source, description, confidence and review flag. -
Preserve history; do not silently overwrite or delete historical events.

**Task** - Title, description, job ID, application ID, task type, due
date, status, priority, external task ID, timestamps. - Internal tasks
must work without Notion.

**JobSearch** - Name, keywords, roles, locations, employment types,
included companies, excluded companies, filters, active status.

**IngestionRun** - URL/source, run status, timestamps, extracted job ID,
errors, retry metadata.

### B. Application statuses

Support: - DISCOVERED - TO_APPLY - PREPARING - APPLIED - ACKNOWLEDGED -
UNDER_REVIEW - OA_RECEIVED - OA_COMPLETED - TECHNICAL_TEST -
INTERVIEW_SCHEDULED - INTERVIEW_COMPLETED - FURTHER_ROUNDS -
OFFER_RECEIVED - REJECTED - WITHDRAWN - CLOSED

Email-originated transitions will be used only in the final email phase.
Manual status changes must work now.

### C. Manual CRUD APIs

Profile: - GET and PUT `/api/v1/profile`. - Create, update, list and
archive resumes.

Companies: - POST, GET, GET by ID, PUT and DELETE/archive.

Company sources: - POST, GET, PUT, DELETE/archive.

Jobs: - POST, GET, GET by ID, PUT, DELETE/archive.

Applications: - POST, GET, GET by ID, PATCH status, GET events.

Tasks: - POST, GET, PUT, PATCH status, DELETE/archive.

Search configurations: - POST, GET, PUT and DELETE/archive.

Provide pagination, filtering, sorting and validation.

### D. Business rules

-   Use soft deletion/archive where history matters.
-   A job may exist without an application.
-   An application must reference an existing job.
-   A job may have several source references.
-   A user may maintain multiple resumes.
-   Manual status changes create ApplicationEvent records.
-   Avoid duplicate company and job records.
-   Use transactions for related updates.
-   Do not expose SQLAlchemy models directly.

### E. Tests

Test all CRUD operations, relationships, invalid inputs, status history,
archive behavior, duplicate prevention and pagination.

Deliver complete API documentation and example requests.

Do not implement scraping, AI matching, Gmail or scheduled discovery
yet.

------------------------------------------------------------------------

## PROMPT 03 --- Phase 2: Individual job URL ingestion and extraction

Implement job URL submission and structured extraction.

### A. API

Implement:

`POST /api/v1/jobs/ingest`

Input:

``` json
{
  "url": "https://example.com/careers/job-123"
}
```

Return: - ingestion ID. - normalized URL. - status. - job ID when
complete. - extraction errors when applicable.

Support background processing for slow pages.

### B. Safe retrieval

-   Accept HTTP and HTTPS only.
-   Block localhost, private IPs, link-local and internal network
    destinations.
-   Validate DNS resolutions and redirects to mitigate SSRF and DNS
    rebinding.
-   Set connection and read timeouts.
-   Limit response size.
-   Use HTTPX first.
-   Use Playwright only when JavaScript rendering is needed.
-   Respect rate limits and access restrictions.
-   Do not bypass CAPTCHAs or authentication.

### C. Extraction methods

Implement: 1. JobPosting JSON-LD extraction. 2. Open Graph and metadata
extraction. 3. Generic visible HTML extraction. 4. Playwright
rendered-page extraction. 5. Ollama-assisted structured extraction.

### D. Ollama extraction

Create an LLM service abstraction:

-   Configurable base URL.
-   Configurable model.
-   Timeout.
-   Retry.
-   JSON/schema validation.
-   Model health check.
-   Prompt version tracking.

Ask Ollama to extract:

-   Company.
-   Role title.
-   Location.
-   Employment type.
-   Workplace type.
-   Experience.
-   Graduation-year eligibility.
-   Degree requirements.
-   Required skills.
-   Preferred skills.
-   Responsibilities.
-   Qualifications.
-   Compensation, if disclosed.
-   Application deadline.
-   Application URL.
-   Description.

Unknown fields must remain null or empty. Never infer an unstated
deadline or eligibility criterion.

### E. Source adapters

Create a common adapter interface.

Initial adapters: - Generic HTML. - JSON-LD. - Greenhouse. - Lever.

Prefer official public job APIs where permitted.

### F. Deduplication

Compare: - Canonical URLs. - Source external IDs. - Company identity. -
Title. - Location. - Job description similarity where necessary.

Do not merge unrelated jobs simply because their titles match.

Preserve all source references.

### G. Dashboard

Add a job submission page: - URL input. - Processing status. - Extracted
job preview. - Editable extracted fields. - Save/approve action. -
Reprocess action.

The user must be able to correct extraction errors before finalizing a
record.

### H. Tests

Use HTML fixtures and mocked Ollama responses. Do not depend on live
sites for normal tests.

Test SSRF protections, JSON-LD, generic pages, missing fields, malformed
LLM output, timeouts and duplicate jobs.

------------------------------------------------------------------------

## PROMPT 04 --- Phase 3: Profile matching, eligibility and internal task creation

Implement job evaluation using Ollama and the user's configurable
profile.

### A. Eligibility first

Evaluate mandatory conditions separately: - Graduation year. - Degree
and branch. - Minimum CGPA. - Experience. - Location. - Work
authorization or sponsorship, where explicitly stated.

Return: - ELIGIBLE. - UNCERTAIN. - INELIGIBLE. - NOT_EVALUATED.

Do not treat missing eligibility data as proof of eligibility.

### B. Relevance scoring

Use an initial configurable weighted model:

`Score = 0.30E + 0.30T + 0.20P + 0.10R + 0.10L`

Where: - E: eligibility compatibility. - T: technical skills
compatibility. - P: projects and experience relevance. - R: role/domain
relevance. - L: location and logistical compatibility.

Each component is scored from 0 to 100.

Mandatory ineligibility must override a high relevance score.

Do not present a score as objective truth. Store its explanation,
evidence and model version.

### C. Evaluation output

Return structured JSON:

``` json
{
  "job_id": "uuid",
  "eligibility_status": "ELIGIBLE",
  "overall_score": 85,
  "component_scores": {
    "eligibility": 90,
    "technical": 85,
    "experience": 80,
    "role_relevance": 90,
    "location": 70
  },
  "matched_skills": [],
  "missing_skills": [],
  "strengths": [],
  "concerns": [],
  "recommendation": "HIGH_PRIORITY",
  "recommended_resume_id": null,
  "explanation": ""
}
```

Values are illustrative. Validate all outputs.

### D. Task creation

Create internal tasks in PostgreSQL.

Examples: - Review job description. - Select resume. - Prepare
application. - Submit application. - Complete assessment. - Follow up.

Do not require Notion for the system to function.

Avoid duplicate tasks. Allow configurable thresholds: - 85+:
Excellent. - 70--84: Good. - 55--69: Review. - Below 55: Low relevance.

Create tasks only according to configurable eligibility and relevance
rules.

### E. Dashboard

Add: - Match score and breakdown. - Eligibility result. - Matched and
missing skills. - Recommended resume. - Explanation and evidence. -
Create application / task controls.

### F. Tests

Test mandatory eligibility failures, missing requirements, different
resume versions, scoring boundaries, malformed model output and
duplicate tasks.

------------------------------------------------------------------------

## PROMPT 05 --- Phase 4: Dynamic company career-page registry

Implement dynamic company career-page registration.

This is a central HydraJob feature.

### A. User-facing registration

The user should be able to add:

-   Company name.
-   Main website.
-   Career-page URL.
-   Industry/category.
-   Notes.
-   Active monitoring toggle.

The user must also be able to edit, disable, re-enable and archive
sources.

### B. Source onboarding

When a source is registered:

1.  Validate the URL.
2.  Inspect the domain.
3.  Identify known ATS platforms.
4.  Inspect permitted public page structure.
5.  Identify available public job API/feed.
6.  Recommend an extraction adapter.
7.  Run a small test scan.
8.  Show sample extracted jobs.
9.  Let the user approve the configuration.
10. Activate the source only after successful validation.

If automatic detection fails, mark it `NEEDS_CONFIGURATION`. Do not
invent an extraction endpoint or generate arbitrary scraper code at
runtime.

### C. Adapter registry

Implement pluggable adapters: - Greenhouse. - Lever. - Ashby where
supported. - Generic public JSON API. - Generic HTML. - JSON-LD. -
Browser-rendered pages.

Prefer official APIs and public job-board feeds over scraping rendered
HTML.

### D. Seed company list

Prepare a seed file with verified career-page URLs for companies across:

Technology: - Google. - Microsoft. - Amazon. - NVIDIA. - Adobe. -
Apple. - Atlassian. - Salesforce. - Qualcomm.

AI: - OpenAI. - Anthropic. - Meta. - Google DeepMind.

Quantitative finance: - Jane Street. - Tower Research Capital. - D. E.
Shaw. - Optiver. - IMC. - Quadeye.

Do not invent URLs. Verify each URL and adapter compatibility. Keep
unverified sources inactive and mark them for review.

### E. APIs

Implement: - Register source. - Test source. - Scan source. - List
sources. - Update source. - Activate/deactivate source. - List jobs from
source. - View scan history.

### F. Tests

Use fixtures for every supported adapter. Test onboarding, failed
configuration, successful test extraction, pagination, rate limits,
duplicate detection and source deactivation.

------------------------------------------------------------------------

## PROMPT 06 --- Phase 5: Career-page scraping and scheduled job discovery

Implement autonomous discovery from registered company sources.

### A. Search configurations

Allow the user to create searches with: - Keywords. - Job categories. -
Locations. - Remote preference. - Employment type. - Graduation year. -
Experience level. - Included/excluded companies. - Minimum match
score. - Active status.

### B. Discovery engine

For each active source: 1. Fetch public listings. 2. Paginate where
supported. 3. Extract job IDs and URLs. 4. Detect new and updated
openings. 5. Extract full job descriptions. 6. Deduplicate. 7. Save
source references. 8. Evaluate jobs using the configured profile. 9.
Create internal tasks according to policy. 10. Record scan results.

### C. Incremental scanning

Track: - First seen. - Last seen. - Last changed. - Last successful
scan. - Extraction status. - Source health.

Do not mark a job closed based on one failed scan. Require sufficient
evidence.

### D. Discovery APIs

Implement endpoints for: - Triggering all active scans. - Triggering one
source. - Triggering one search. - Listing scan runs. - Viewing newly
discovered jobs. - Viewing failed sources.

Do not put scheduler logic inside business services. n8n will trigger
these APIs in a later phase.

### E. Reliability

-   Per-domain rate limiting.
-   Retry with exponential backoff.
-   Bounded concurrency.
-   Source-specific failure isolation.
-   Idempotent runs.
-   Structured logging.
-   Manual retry controls.

### F. Tests

Use offline fixtures and mocked HTTP responses. Include pagination, new
listings, updated listings, closed jobs, failures and deduplication.

------------------------------------------------------------------------

## PROMPT 07 --- Phase 6: Streamlit dashboard and manual management UX

Build a complete dashboard using FastAPI APIs only.

### Pages

**1. Overview** - Jobs discovered. - High-priority jobs. - Applications
to prepare. - Applications submitted. - Upcoming deadlines. - Recent
source scans. - Failed sources.

**2. Jobs** - Search and filter. - View extracted descriptions. - Edit
all fields. - Archive jobs. - Evaluate or re-evaluate. - Create
application.

**3. Submit Job URL** - Submit URL. - Show ingestion progress. - Preview
extraction. - Edit extracted fields. - Approve/save. - Reprocess.

**4. Companies** - Add/edit/archive companies. - View company jobs. -
View career pages. - View notes.

**5. Career Sources** - Add/edit/disable sources. - Test a career
page. - Scan now. - View last successful scan. - Review failures. -
Inspect extracted openings.

**6. Profile and Resumes** - Edit education, graduation year, CGPA,
skills, roles and locations. - Upload multiple resumes. - Mark preferred
resume versions. - Review extracted resume skills.

**7. Applications** - Kanban-style application pipeline. - Job
details. - Resume used. - Match score. - Status history. - Notes. -
Manual status changes.

**8. Tasks** - To Apply. - Preparing. - Applied. - Assessment. -
Interview preparation. - Follow-up.

**9. Search Configuration** - Create/edit searches. - Configure keywords
and filters. - Enable/disable searches.

**10. System Health** - Backend status. - Database status. - Ollama
status and selected model. - n8n status. - Last scan times. - Failed
jobs and retries.

### UX requirements

-   Professional and uncluttered.
-   Responsive.
-   No unnecessary emojis.
-   Clear loading and error states.
-   Asia/Kolkata display timezone.
-   Pagination and filters.
-   Confirm destructive actions.
-   Do not expose credentials or raw email content.

Test all major pages and user operations.

------------------------------------------------------------------------

## PROMPT 08 --- Phase 7: n8n orchestration and AWS deployment hardening

Implement n8n workflows after the core backend and dashboard are stable.

### Workflow 1: Manual job intake

Webhook receives a URL, calls job ingestion, waits for completion and
triggers evaluation.

### Workflow 2: Scheduled company scans

Schedule trigger retrieves active sources, triggers scans and records
results. One source failure must not stop the rest.

### Workflow 3: Search execution

Trigger configured searches, evaluate new jobs and create tasks.

### Workflow 4: Retry and failure handling

Identify failed ingestion and source runs, retry within bounded limits
and expose unresolved failures in the dashboard.

### n8n requirements

-   Export workflows as JSON in `n8n/workflows/`.
-   Never export credentials or secrets.
-   Use authenticated internal API calls.
-   Use stable webhook paths.
-   Add retries and error workflows.
-   Avoid duplicate executions.
-   Keep business logic in Python.

### AWS production deployment

Document and verify: - EC2 instance setup. - EBS persistent volumes. -
Docker and Compose installation. - Security groups. - HTTPS and reverse
proxy. - n8n public URL and webhook URL. - Database backup/restore. -
Ollama private networking. - Model persistence. - Service restart
policies. - Log rotation. - AWS budget alerts. - Upgrade and rollback
procedure.

Do not expose PostgreSQL or Ollama publicly.

Do not claim deployment success unless actually performed and verified.

------------------------------------------------------------------------

## PROMPT 09 --- Final phase: Gmail integration and recruitment email intelligence

Do not begin this phase until job intake, career-page discovery,
matching and application tracking are stable.

Implement Gmail OAuth and recruitment email tracking.

### Gmail integration

-   Gmail API.
-   Read-only access initially.
-   Dedicated recruitment label/filter.
-   Message and thread IDs.
-   Incremental synchronization checkpoints.
-   No email sending or deletion.

### Classifications

-   Application acknowledgement.
-   Application received.
-   Under review.
-   Online assessment invitation.
-   Assessment reminder.
-   Assessment completed.
-   Technical test.
-   Interview invitation.
-   Interview reschedule.
-   Interview feedback.
-   Next round.
-   Rejection.
-   Offer.
-   Document request.
-   Information request.
-   Withdrawal.
-   Non-recruitment.
-   Unknown.

### Matching

Match by sender domain, company, job title, application reference,
thread ID and application history.

Support multiple applications at one company. If ambiguous, request
manual review.

### Confidence policy

-   0.90 or above: Automatic status update only if application
    association is also unambiguous.
-   0.70--0.89: Review queue.
-   Below 0.70: No automatic update.

### Event history

Every recognized email event must be recorded in ApplicationEvent. Never
overwrite the historical sequence.

Do not log full email bodies or retain unnecessary sensitive content.

### Dashboard

Add: - Recent recruitment messages. - Event classifications. - Linked
applications. - Confidence. - Review queue. - Manual correction and
linking.

### Tests

Use synthetic emails. Test OA, interviews, rejection, offers, ambiguous
matching, duplicate messages and status regression prevention.

------------------------------------------------------------------------

# 7. Required completion report for every phase

At the end of each phase, provide:

1.  **Implementation summary:** What was actually built.
2.  **Files changed:** New, modified and deleted files.
3.  **Architecture changes:** Any justified deviation from the plan.
4.  **Database changes:** Models and migrations.
5.  **API changes:** Endpoints and example requests.
6.  **Tests:** Commands executed and actual pass/fail results.
7.  **Deployment:** Commands needed to run the updated system.
8.  **Known issues:** Limitations and unfinished work.
9.  **Security review:** Secrets, exposed ports and external access.
10. **Next phase readiness:** Whether the phase is genuinely complete.

Do not proceed automatically to the next phase.

------------------------------------------------------------------------

# 8. Initial AWS and Ollama deployment guidance

Before choosing an EC2 instance, inspect the AWS credit balance, credit
expiration and eligible services.

Do not choose an instance solely because it is advertised as free-tier
eligible. Ollama is the resource-intensive component.

A practical sizing approach:

  -----------------------------------------------------------------------
  Workload                            Planning guidance
  ----------------------------------- -----------------------------------
  Backend + PostgreSQL + n8n +        Small general-purpose instance may
  dashboard, no Ollama                suffice

  Small quantized 3B model            Test with available RAM; allow
                                      memory for all other services

  Quantized 7B model                  Prefer approximately 16 GB RAM or
                                      more, then benchmark

  Larger 14B model                    Consider 32 GB RAM or more

  GPU inference                       Consider only after measuring CPU
                                      latency and workload
  -----------------------------------------------------------------------

These are planning estimates, not guarantees. Actual requirements depend
on quantization, context length, concurrency and model architecture.

For initial development, select one small instruct model supported by
Ollama, pull it explicitly, and run extraction tests before selecting a
larger model.

Keep `OLLAMA_BASE_URL` and `OLLAMA_MODEL` configurable. This permits
moving Ollama to another EC2 instance later.

------------------------------------------------------------------------

# 9. Definition of the first usable HydraJob release

The first useful release is complete when the user can:

1.  Open the Streamlit dashboard.
2.  Add and edit a company.
3.  Register and test its career page.
4.  Submit an individual job URL.
5.  Extract a structured job description.
6.  Correct extracted information manually.
7.  Save the job to PostgreSQL.
8.  Evaluate it using an Ollama model.
9.  View match scores and eligibility.
10. Create an application and tasks.
11. Scan registered career pages on demand.
12. See newly discovered jobs and avoid duplicates.
13. Keep the system running on AWS without depending on the user's
    laptop.

Gmail is not required for this release.

**Build toward this first usable release before adding advanced agent
frameworks or email automation.**
