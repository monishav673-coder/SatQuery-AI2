# SATQUERY AI — Production Deployment Checklist

## Environment
- [ ] SECRET_KEY set to 64+ character random string (not the default)
- [ ] JWT_SECRET_KEY set to different 64+ character random string
- [ ] DATABASE_URL points to PostgreSQL (not SQLite)
- [ ] REDIS_URL configured and Redis reachable
- [ ] CORS_ORIGINS set to actual production domain only
- [ ] DEMO_MODE=false
- [ ] DEBUG=false
- [ ] FLASK_ENV=production

## Database
- [ ] PostgreSQL running and accessible from backend container
- [ ] `alembic upgrade head` ran successfully
- [ ] Database backup strategy configured
- [ ] POSTGRES_PASSWORD is a strong random string

## Infrastructure
- [ ] SSL certificates installed in docker/ssl/
- [ ] docker/nginx.prod.conf updated with correct domain name
- [ ] `docker compose -f docker-compose.prod.yml build` succeeds
- [ ] `docker compose -f docker-compose.prod.yml up -d` starts all services
- [ ] `docker compose -f docker-compose.prod.yml ps` shows all services healthy

## Health Checks
- [ ] `curl https://yourdomain.com/health` returns `{"status":"ok"}`
- [ ] `curl https://yourdomain.com/ready` shows database=ok and storage=ok
- [ ] `curl https://yourdomain.com/api/models` shows expected model statuses

## Authentication
- [ ] User registration works
- [ ] User login returns JWT token
- [ ] JWT-protected endpoints require valid token
- [ ] Password hashing confirmed (no plaintext in DB)
- [ ] Rate limiting active on login endpoint

## OTP / Password Reset
- [ ] SMS_PROVIDER configured (not "development")
- [ ] OTP sends to real mobile number
- [ ] OTP verification works
- [ ] Password reset completes successfully
- [ ] OTP is NOT logged or exposed in responses

## Satellite Provider
- [ ] SATELLITE_PROVIDER configured
- [ ] Credentials valid (test with a known coordinate)
- [ ] No imagery returned when provider unavailable (honest message)

## ML Models
- [ ] BLIP status at /api/models shows CONFIGURED or NOT_CONFIGURED (not FAILED)
- [ ] BLIP VQA status confirmed
- [ ] Grounding DINO weights file exists at configured path
- [ ] Building count is null (not fabricated) when DINO not configured
- [ ] BigEarthNet model path valid if BIGEARTHNET_ENABLED=true
- [ ] Change detection runs (image differencing fallback at minimum)
- [ ] SAR model configured if SAR_ANALYSIS_ENABLED=true

## Analysis Pipeline
- [ ] Single image upload and analysis completes
- [ ] Multitemporal analysis with change detection completes
- [ ] Coordinate-based analysis returns honest "no imagery" if provider unconfigured
- [ ] Natural language query returns evidence-grounded answer
- [ ] PDF report downloads correctly
- [ ] No fabricated values in results (check building_count=null, limitations present)

## Worker
- [ ] RQ worker container running (`docker compose ps worker`)
- [ ] Worker processes analysis jobs (check `docker compose logs worker`)
- [ ] SSE progress stream works in browser

## Security
- [ ] Security headers present (X-Frame-Options, X-Content-Type-Options, CSP)
- [ ] HSTS header present (requires HTTPS)
- [ ] No secrets in response bodies or logs
- [ ] File upload rejects invalid MIME types
- [ ] Path traversal not possible via upload filenames
- [ ] CORS rejects requests from unauthorized origins

## Frontend
- [ ] Login page loads with 3D Earth (or CSS fallback)
- [ ] All analysis modes work
- [ ] Empty states shown (not fake values) when model unavailable
- [ ] Model status page (/models) shows accurate statuses
- [ ] SSE progress stream updates during analysis

## Monitoring
- [ ] Docker container logs accessible
- [ ] Health check endpoint monitored
- [ ] Worker queue depth observable
- [ ] Alerts configured for service failures
