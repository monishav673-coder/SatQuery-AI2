# SATQUERY AI — Production Deployment Guide

## Overview
This guide covers deploying SATQUERY AI to a production server using Docker Compose.

---

## Prerequisites

- Ubuntu 22.04 LTS (or similar Linux)
- Docker Engine 24+ and Docker Compose v2
- 4 GB RAM minimum (8 GB recommended with ML models)
- 50 GB disk space
- A domain name with DNS pointing to your server
- SSL certificate (Let's Encrypt recommended)

---

## Step 1 — Provision server

```bash
# Update packages
apt-get update && apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Verify
docker --version
docker compose version
```

---

## Step 2 — Clone the repository

```bash
cd /opt
git clone https://github.com/your-org/satquery-ai.git
cd satquery-ai
```

---

## Step 3 — Configure environment

```bash
cp backend/.env.example .env.production
nano .env.production
```

**Required variables (must set):**
```env
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
JWT_SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
DATABASE_URL=postgresql://satquery:<password>@postgres:5432/satquery_db
REDIS_URL=redis://redis:6379/0
POSTGRES_PASSWORD=<strong-random-password>
CORS_ORIGINS=https://yourdomain.com
```

**Optional but recommended:**
```env
SATELLITE_PROVIDER=sentinel_hub
SENTINEL_HUB_CLIENT_ID=<your-id>
SENTINEL_HUB_CLIENT_SECRET=<your-secret>
GEOCODING_PROVIDER=nominatim
CHANGE_DETECTION_ENABLED=true
SMS_PROVIDER=<twilio|fast2sms|msg91>
SMS_PROVIDER_API_KEY=<your-key>
```

---

## Step 4 — Configure HTTPS

```bash
# Install certbot
apt-get install certbot -y
certbot certonly --standalone -d yourdomain.com

# Copy certificates to docker/ssl/
mkdir -p docker/ssl
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem docker/ssl/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem docker/ssl/
chmod 600 docker/ssl/*.pem
```

---

## Step 5 — Configure ML models (optional)

To enable real ML inference, download model weights and configure paths:

**BLIP / BLIP VQA:**
```env
BLIP_ENABLED=true
BLIP_VQA_ENABLED=true
# Models auto-downloaded from Hugging Face on first request
MODEL_CACHE_DIR=/app/backend/.model_cache
```

**Grounding DINO (object detection):**
```bash
# Download weights
wget https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth \
  -O docker/models/groundingdino_swint_ogc.pth
```
```env
GROUNDING_DINO_ENABLED=true
GROUNDING_DINO_WEIGHTS_PATH=/app/backend/models/groundingdino_swint_ogc.pth
```

**BigEarthNet classifier:**
```env
BIGEARTHNET_ENABLED=true
BIGEARTHNET_MODEL_PATH=/app/backend/models/bigearthnet_model.onnx
BIGEARTHNET_NUM_CLASSES=19
```

---

## Step 6 — Build containers

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build
```

---

## Step 7 — Start services

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

---

## Step 8 — Run database migrations

```bash
docker compose -f docker-compose.prod.yml exec backend \
  alembic upgrade head
```

---

## Step 9 — Verify health

```bash
# Liveness check
curl -s https://yourdomain.com/health

# Readiness check (checks DB, Redis, storage)
curl -s https://yourdomain.com/ready

# Model status
curl -s https://yourdomain.com/api/models
```

Expected liveness response:
```json
{"status": "ok", "app": "SATQUERY AI", "version": "2.0.0"}
```

---

## Step 10 — Test login

```bash
curl -X POST https://yourdomain.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Admin","email":"admin@yourdomain.com","password":"SecurePass123","confirm_password":"SecurePass123"}'
```

---

## Step 11 — Monitor logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Backend only
docker compose -f docker-compose.prod.yml logs -f backend

# Worker only
docker compose -f docker-compose.prod.yml logs -f worker
```

---

## Production commands reference

```bash
# Status
docker compose -f docker-compose.prod.yml ps

# Restart a service
docker compose -f docker-compose.prod.yml restart backend

# Scale workers
docker compose -f docker-compose.prod.yml up -d --scale worker=4

# Stop all
docker compose -f docker-compose.prod.yml down

# Remove volumes (DESTRUCTIVE — loses data)
docker compose -f docker-compose.prod.yml down -v
```

---

## PostgreSQL backup

```bash
# Backup
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U satquery satquery_db > backup_$(date +%Y%m%d).sql

# Restore
cat backup.sql | docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U satquery satquery_db
```

---

## Deployment Checklist

```
[ ] SECRET_KEY configured (long random string, not default)
[ ] JWT_SECRET_KEY configured (different from SECRET_KEY)
[ ] DATABASE_URL set to PostgreSQL
[ ] POSTGRES_PASSWORD set (strong)
[ ] REDIS_URL configured
[ ] CORS_ORIGINS set to your domain only
[ ] HTTPS certificates installed
[ ] docker/nginx.prod.conf updated with your domain
[ ] docker compose build successful (no errors)
[ ] alembic upgrade head ran successfully
[ ] /health returns {"status":"ok"}
[ ] /ready returns all required checks OK
[ ] Login and registration tested
[ ] Upload and analysis tested
[ ] Worker processes analysis jobs (check docker logs worker)
[ ] SMS_PROVIDER configured if OTP is required
[ ] SATELLITE_PROVIDER configured if coordinate analysis required
[ ] ML models configured and status visible at /api/models
[ ] Security headers present in responses
[ ] Log files not exposing secrets
```

---

## GPU setup (optional)

To enable GPU inference:
```bash
# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list > /etc/apt/sources.list.d/nvidia-docker.list
apt-get update && apt-get install -y nvidia-docker2
systemctl restart docker
```

Then in docker-compose.prod.yml, add to the worker service:
```yaml
deploy:
  resources:
    reservations:
      devices:
        - capabilities: [gpu]
```

Set `MODEL_DEVICE=cuda` in your `.env.production`.

---

## Troubleshooting

**Backend won't start:**
- Check `docker compose logs backend` for missing env vars
- Ensure DATABASE_URL is reachable from the backend container
- Run `alembic upgrade head` if DB tables are missing

**Worker not processing jobs:**
- Check `docker compose logs worker`
- Verify REDIS_URL matches between backend and worker

**Model not loading:**
- Confirm model weights exist at the configured path
- Check `docker compose exec backend python -c "from ml_service.registry import list_models_status; print(list_models_status())"`

**Analysis stuck in 'processing':**
- Worker may have crashed — check `docker compose logs worker`
- Without Redis, analysis runs synchronously and should complete inline

**OTP not sending:**
- Confirm SMS_PROVIDER and SMS_PROVIDER_API_KEY are set correctly
- Check provider dashboard for delivery status
- In development only: set `SMS_PROVIDER=development` to see OTP in logs

---

## Security notes

- Never use `DEBUG=true` in production
- Rotate SECRET_KEY and JWT_SECRET_KEY regularly
- Keep SSL certificates renewed (use certbot renew cron job)
- Restrict SSH access to known IPs
- Review Nginx logs for anomalous patterns
- Database password should be 32+ characters
- Set up automated PostgreSQL backups
