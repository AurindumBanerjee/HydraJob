# HydraJob AWS EC2 Deployment & Hardening Guide

This guide covers deploying HydraJob on a single AWS EC2 instance using Docker Compose, Amazon EBS (`gp3`) persistent storage, Caddy automatic HTTPS, n8n webhook routing, log rotation, and backup/rollback procedures.

> **Important:** Verify your AWS account's billing status and promotional credit eligibility/expiration in the AWS Billing Console before provisioning paid resources. Open-source software (Docker, PostgreSQL, Ollama, n8n, Caddy) has no license fee, but EC2 compute, EBS storage, Elastic IP, and outbound data transfer incur AWS charges.

---

## 1. EC2 Prerequisites & Instance Sizing

### Ollama RAM & Model-Size Considerations

Running Ollama locally on EC2 requires sizing RAM for model weights, KV-cache/context window, and OS + stack overhead (`postgres`, `backend`, `dashboard`, `n8n`, `caddy`):

| Workload Profile | Suggested Model | Model RAM Footprint | Recommended EC2 Instance |
| :--- | :--- | :--- | :--- |
| Lightweight dev / smoke test | `qwen2.5:3b-instruct` (Q4) | ~2.5–3.5 GB | `t3.large` / `t3a.large` (2 vCPU, 8 GB RAM) |
| Recommended CPU baseline | `qwen2.5:7b-instruct` / `llama3.1:8b` (Q4_K_M) | ~5–7 GB + context | `t3a.xlarge` or `m6i.xlarge` (4 vCPU, 16 GB RAM) |
| Larger local models (14B+) or low latency | `qwen2.5:14b` or GPU inference | ~10–16+ GB | `m6i.2xlarge` (32 GB RAM) or GPU instance (`g5.xlarge`, 24 GB VRAM) |

- **Avoid `t2.micro`/`t3.micro`/`t3.small` for Ollama:** 1–2 GB RAM instances will OOM-kill when loading 7B models.
- **CPU vs GPU:** CPU-only instances (`16 GB` RAM) work for asynchronous background extraction/matching, though inference takes tens of seconds per call. Configure `OLLAMA_REQUEST_TIMEOUT` accordingly (e.g., `60.0`–`120.0`). Moving Ollama to a dedicated private GPU EC2 instance later only requires changing `OLLAMA_BASE_URL`.

### Prerequisites

- Ubuntu Server 24.04 LTS (or Amazon Linux 2023) AMI (`x86_64` or `arm64`)
- Elastic IP + static DNS A-record pointing your domain (e.g., `hydrajob.example.com`) to the EC2 public IP for Let's Encrypt HTTPS
- AWS Systems Manager (SSM) Session Manager IAM role attached to the EC2 instance (preferred over opening SSH port 22)

---

## 2. EBS Volume Planning

Allocate an Amazon EBS `gp3` root/data volume sized for OS, Docker images, PostgreSQL data, n8n state, and Ollama model weights:

- **OS + Docker images:** ~15–20 GB
- **Ollama models (`ollama_data`):** ~5–15 GB per 7B–14B quantized model
- **PostgreSQL (`postgres_data`) + WAL + backups:** ~10–20 GB
- **n8n (`n8n_data`) + rotated logs + swap:** ~5–10 GB

**Recommended minimum:** **60 GB–100 GB `gp3`** (3,000 baseline IOPS, 125 MB/s throughput). Enable EBS encryption at rest.

---

## 3. Security Groups

Configure the EC2 Security Group with minimal inbound rules:

| Direction | Port / Protocol | Source | Purpose |
| :--- | :--- | :--- | :--- |
| Inbound | `80/tcp` | `0.0.0.0/0` (or restricted IP) | HTTP (ACME challenge & redirect to HTTPS) |
| Inbound | `443/tcp` | `0.0.0.0/0` (or your static IP/VPN) | HTTPS via Caddy |
| Inbound | `443/udp` | `0.0.0.0/0` (optional) | HTTP/3 (QUIC) via Caddy |
| Inbound | `22/tcp` | **Closed** (use AWS SSM Session Manager, or restrict strictly to your `/32` IP) | Administration |
| Inbound | `5432`, `11434`, `8000`, `8501`, `5678` | **NEVER OPEN** | Internal Docker services only |
| Outbound | All | `0.0.0.0/0` | Package updates, Let's Encrypt, permitted career-page fetching |

---

## 4. Docker Installation & Log Rotation (Ubuntu 24.04)

Connect via AWS SSM Session Manager and install Docker Engine + Docker Compose plugin from Docker's official repository:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git python3 python3-yaml
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

### Configure Docker Daemon Log Rotation

Prevent container JSON logs from filling the EBS volume by configuring `/etc/docker/daemon.json` before starting services:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "20m",
    "max-file": "5"
  }
}
```

Apply and verify:

```bash
sudo systemctl restart docker
docker --version
docker compose version
```

---

## 5. Production Compose Deployment & n8n URL Hardening

1. Clone the repository on the instance (e.g., `/opt/hydrajob`):
   ```bash
   git clone <your-repo-url> /opt/hydrajob
   cd /opt/hydrajob
   ```
2. Create `.env` from `.env.example` and lock down permissions:
   ```bash
   cp .env.example .env
   chmod 600 .env
   python3 supporting_codes/generate_secrets.py
   ```
3. Generate a Caddy bcrypt password hash for Basic Auth:
   ```bash
   docker run --rm caddy:2-alpine caddy hash-password --plaintext 'REPLACE_WITH_STRONG_PASSWORD'
   ```
   When placing the hash into `.env` for `CADDY_BASIC_AUTH_HASH`, escape every `$` as `$$` so Docker Compose does not treat `$2a$14$...` as variable interpolation.
4. Configure production, Caddy, and n8n public/webhook URL variables in `.env`:
   ```env
   APP_ENV=production
   DOMAIN_NAME=hydrajob.example.com
   N8N_HOST=hydrajob.example.com
   N8N_PROTOCOL=https
   N8N_WEBHOOK_URL=https://hydrajob.example.com/n8n/
   N8N_SECURE_COOKIE=true
   DATABASE_URL=postgresql+psycopg://hydrajob:<POSTGRES_PASSWORD>@postgres:5432/hydrajob
   ```
   > If using a dedicated subdomain (e.g., `n8n.hydrajob.example.com`) uncomment the subdomain block in `Caddyfile` and set `N8N_HOST=n8n.hydrajob.example.com` and `N8N_WEBHOOK_URL=https://n8n.hydrajob.example.com/`.
5. Validate the merged production configuration:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile production config
   python3 supporting_codes/verify_compose.py
   ```
   Confirm `postgres`, `ollama`, `backend`, `dashboard`, and `n8n` have **no** published host ports and only `caddy` publishes `80` and `443`.
6. Build and launch the production stack (all services use `restart: unless-stopped`):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d --build
   ```
7. Run Alembic migrations, verify model pull explicitly, and import n8n workflows:
   ```bash
   docker compose exec backend alembic upgrade head
   docker compose exec ollama ollama pull qwen2.5:7b-instruct
   docker compose exec ollama ollama list
   ```
   Then seed initial companies/searches if desired (`python3 supporting_codes/seed_initial_data.py --apply`) and configure n8n `HydraJob X-API-Key` credentials per [n8n/README.md](../n8n/README.md).

---

## 6. Persistent Storage, Private Networking & HTTPS

- **Named Docker Volumes** (`postgres_data`, `ollama_data`, `n8n_data`, `caddy_data`, `caddy_config`) persist on the EBS volume under `/var/lib/docker/volumes/`.
- **Service Restart Policies:** Every service in `docker-compose.yml` sets `restart: unless-stopped` so containers recover cleanly from crashes or EC2 reboots.
- **Ollama Private Networking & Model Persistence:** `ollama` attaches only to `hydrajob_internal` (`expose: ["11434"]`, zero `ports:`) and persists downloaded weights in `ollama_data:/root/.ollama` without auto-pulling on container boot.
- **Caddy HTTPS:** Caddy automatically obtains and renews Let's Encrypt TLS certificates for `DOMAIN_NAME` and protects `/` and `/n8n/*` with Basic Auth, while `/api/*` requires `X-API-Key`.

---

## 7. Backups & Restore

### PostgreSQL Logical Backup (`pg_dump`)

Back up both `hydrajob` and `n8n` databases regularly (e.g., daily cron job copying encrypted dumps to S3):

```bash
mkdir -p backups
docker compose exec -T postgres pg_dump -U hydrajob -Fc hydrajob > "backups/hydrajob_$(date +%F_%H%M).dump"
docker compose exec -T postgres pg_dump -U hydrajob -Fc n8n > "backups/n8n_$(date +%F_%H%M).dump"
```

Back up `.env` (specifically `N8N_ENCRYPTION_KEY`, `APP_SECRET_KEY`, and `APP_API_KEY`) in AWS Secrets Manager or an encrypted offline vault—never in Git.

### PostgreSQL Restore (`pg_restore`)

```bash
docker compose exec -T postgres pg_restore -U hydrajob --clean --if-exists -d hydrajob < backups/hydrajob_YYYY-MM-DD_HHMM.dump
docker compose exec -T postgres pg_restore -U hydrajob --clean --if-exists -d n8n < backups/n8n_YYYY-MM-DD_HHMM.dump
```

### EBS Snapshots

Configure **AWS Data Lifecycle Manager (DLM)** to take daily automated EBS snapshots of the instance volume with a 7–14 day retention policy for point-in-time disaster recovery.

---

## 8. Updating & Rollback Procedure

1. Record the current Git commit SHA and Alembic revision before updating:
   ```bash
   git rev-parse HEAD
   docker compose exec backend alembic current
   ```
2. Take a fresh `pg_dump` backup (Section 7).
3. Pull updates, rebuild containers, and apply Alembic migrations:
   ```bash
   git pull --ff-only
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d --build
   docker compose exec backend alembic upgrade head
   ```
4. Verify health checks (`docker compose ps` and `curl -fsS https://$DOMAIN_NAME/health/ready`).
5. **Rollback:** If a release fails verification:
   ```bash
   # Downgrade only if the failed release applied a new migration:
   docker compose exec backend alembic downgrade <previous-revision>
   git checkout <previous-commit-sha>
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d --build
   ```

---

## 9. AWS Budget Alerts

Set up **AWS Budgets** immediately after provisioning:
1. Open **AWS Billing and Cost Management -> Budgets -> Create budget**.
2. Choose **Cost budget** with a monthly threshold matching your comfort limit (e.g., `$20`–`$50/month`).
3. Configure email/SNS notifications at **50%**, **80%**, and **100%** of forecasted and actual spend.
4. Monitor AWS Credits separately under **Billing -> Credits** so you are alerted before credits expire.
