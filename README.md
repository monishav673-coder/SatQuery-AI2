# SATQUERY AI v2.0
### Evidence-Grounded Agentic AI Satellite Intelligence Platform

SATQUERY AI is a production-ready satellite image analysis platform. It accepts uploaded imagery or geographic coordinates, runs a multi-stage agentic AI pipeline, validates every analytical claim with full provenance, and generates PDF reports — all with honest status reporting.

**Every result is either computed from real data or explicitly marked NOT AVAILABLE.**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      SATQUERY AI                             │
│                                                             │
│  Frontend (HTML/JS/CSS + Leaflet + Three.js)                │
│       ↓ HTTP / SSE                                          │
│  Backend (Flask + SQLAlchemy + JWT + Rate Limiting)         │
│       ↓                    ↓ async queue                    │
│  Sync Pipeline        RQ Worker ← Redis                     │
│       ↓                    ↓                                │
│  Agentic Pipeline (12 stages)                               │
│       ↓                                                     │
│  ML Model Registry                                          │
│    ├── BLIP Captioning      (Hugging Face)                  │
│    ├── BLIP VQA             (Hugging Face)                  │
│    ├── Grounding DINO       (IDEA Research)                 │
│    ├── BigEarthNet Classifier (pluggable)                   │
│    ├── Change Detection     (pluggable / image-diff fallback)│
│    └── SAR Analysis         (pluggable)                     │
│       ↓                                                     │
│  Evidence Validator (provenance for every claim)            │
│       ↓                                                     │
│  PostgreSQL / SQLite  +  ReportLab PDF                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start (Development — no Docker)

### 1. Prerequisites
- Python 3.10+
- pip

### 2. Install dependencies

```bash
cd SATQUERY-AI/backend
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — change SECRET_KEY and JWT_SECRET_KEY at minimum
```

### 4. Run the server

```bash
cd backend
python app.py
```

Open **http://127.0.0.1:5000** → redirects to the login page.

---

## Docker (Recommended)

### Development

```bash
docker compose up --build
```

### Production

```bash
# 1. Configure environment
cp backend/.env.example .env.production
nano .env.production   # fill in all required values

# 2. Add SSL certificates
mkdir -p docker/ssl
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem docker/ssl/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem docker/ssl/

# 3. Build and start
docker compose -f docker-compose.prod.yml --env-file .env.production build
docker compose -f docker-compose.prod.yml --env-file .env.production up -d

# 4. Run migrations
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head

# 5. Verify
curl https://yourdomain.com/health
curl https://yourdomain.com/ready
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | ✓ | — | Flask secret key (32+ chars) |
| `JWT_SECRET_KEY` | ✓ | — | JWT signing key |
| `DATABASE_URL` | ✓ prod | SQLite | PostgreSQL URL for production |
| `REDIS_URL` | optional | — | Enables async jobs + SSE progress |
| `CORS_ORIGINS` | optional | localhost | Allowed origins (comma-separated) |
| `SATELLITE_PROVIDER` | optional | none | `sentinel_hub` or `usgs_ee` |
| `BLIP_ENABLED` | optional | false | Enable BLIP captioning model |
| `BLIP_VQA_ENABLED` | optional | false | Enable BLIP VQA model |
| `GROUNDING_DINO_ENABLED` | optional | false | Enable object detection |
| `CHANGE_DETECTION_ENABLED` | optional | true | Enable change detection (image-diff always available) |
| `SMS_PROVIDER` | optional | — | `twilio`, `fast2sms`, `msg91`, `textlocal` |

See `backend/.env.example` for all variables with documentation.

---

## Analysis Modes

### Single Image Analysis
Upload one satellite image → land cover, water, agriculture, buildings.

### Optical + SAR Analysis
Upload optical + SAR image pair → multimodal fusion analysis.

### Multitemporal Change Detection
Upload before + after images → change detection and classification.

### Analyze by Location
Enter latitude/longitude → retrieve imagery via configured provider → full pipeline.

---

## ML Model Setup

### BLIP / BLIP VQA (Image Captioning & Q&A)
```env
BLIP_ENABLED=true
BLIP_VQA_ENABLED=true
# Models auto-downloaded from Hugging Face (~900MB each)
```
```bash
pip install transformers torch
```

### Grounding DINO (Building / Object Detection)
```bash
pip install groundingdino-py
# Download weights:
wget https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth
```
```env
GROUNDING_DINO_ENABLED=true
GROUNDING_DINO_WEIGHTS_PATH=/path/to/groundingdino_swint_ogc.pth
```

### BigEarthNet Classifier (Land Cover — 19 classes)
```env
BIGEARTHNET_ENABLED=true
BIGEARTHNET_MODEL_PATH=/path/to/bigearthnet_model.onnx  # or .pt
BIGEARTHNET_NUM_CLASSES=19
```
Dataset: https://bigearth.net/ (~65 GB)

### Change Detection
Image-differencing fallback works without any model. For a trained model:
```env
CHANGE_DETECTION_MODEL_PATH=/path/to/change_model.pt
```

---

## Satellite Provider Setup

### Sentinel Hub
1. Create account at https://www.sentinel-hub.com/
2. Create an OAuth client
```env
SATELLITE_PROVIDER=sentinel_hub
SENTINEL_HUB_CLIENT_ID=your-client-id
SENTINEL_HUB_CLIENT_SECRET=your-client-secret
```

### USGS Earth Explorer
1. Register at https://earthexplorer.usgs.gov/
```env
SATELLITE_PROVIDER=usgs_ee
USGS_EE_USERNAME=your-username
USGS_EE_PASSWORD=your-password
```

---

## SMS / OTP Setup (Password Reset)

```env
SMS_PROVIDER=twilio   # or fast2sms, msg91, textlocal
SMS_PROVIDER_API_KEY=your-api-key
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_FROM_NUMBER=+1xxxxxxxxxx
```

**Development mode** (prints OTP to server logs only):
```env
SMS_PROVIDER=development  # NEVER use in production
```

---

## Database Migrations

```bash
# Create a new migration after model changes
cd backend
alembic revision --autogenerate -m "description of change"

# Apply all migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

---

## Running Tests

```bash
# From project root
python run_tests.py

# With coverage
cd backend
python -m pytest ../tests/ --cov=. --cov-report=html
```

Tests cover: authentication, API endpoints, agent pipeline, evidence validation, satellite service, OTP security.

---

## GPU Setup

```bash
# Install CUDA-enabled PyTorch
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Set in .env
MODEL_DEVICE=cuda
```

The model registry detects `torch.cuda.is_available()` and reports actual device used. GPU is never claimed if CUDA is unavailable.

---

## API Reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | — | Register account |
| POST | `/api/auth/login` | — | Login → JWT token |
| POST | `/api/auth/logout` | ✓ | Invalidate token |
| GET | `/api/auth/me` | ✓ | Current user |
| PUT | `/api/auth/profile` | ✓ | Update name/language/password |
| POST | `/api/auth/forgot-password` | — | Request OTP |
| POST | `/api/auth/verify-otp` | — | Verify OTP |
| POST | `/api/auth/reset-password` | — | Set new password |
| POST | `/api/analyze/single` | ✓ | Single image analysis |
| POST | `/api/analyze/optical-sar` | ✓ | Optical + SAR analysis |
| POST | `/api/analyze/multitemporal` | ✓ | Change detection |
| POST | `/api/analyze/coordinates` | ✓ | Coordinate analysis |
| POST | `/api/analyze/coordinates/multitemporal` | ✓ | Coordinate change detection |
| GET | `/api/analysis/history` | ✓ | Analysis history |
| GET | `/api/analysis/<id>` | ✓ | Single analysis result |
| DELETE | `/api/analysis/<id>` | ✓ | Delete analysis |
| GET | `/api/analysis/<id>/progress` | ✓ | SSE progress stream |
| POST | `/api/query` | ✓ | Natural language query |
| GET | `/api/report/<id>` | ✓ | Download PDF report |
| GET | `/api/models` | — | Model status |
| GET | `/health` | — | Liveness check |
| GET | `/ready` | — | Readiness check |

---

## Security Notes

- Passwords hashed with bcrypt (12 rounds dev, 14 rounds prod)
- JWT tokens — 24h access, 30d refresh
- OTP hashed with HMAC-SHA256, never stored plaintext
- Security headers: CSP, X-Frame-Options, X-Content-Type-Options
- Rate limiting on auth endpoints
- File upload: MIME validation, size limits, randomized server filenames
- CORS restricted to configured origins (no wildcards in production)
- All analytical values have provenance — never fabricated

---

## Limitations (Honest)

| Capability | Status |
|---|---|
| Land cover (heuristic) | WORKING — spectral brightness proxy |
| Land cover (trained model) | NOT CONFIGURED — set LANDCOVER_MODEL_PATH |
| Water detection | WORKING — brightness heuristic |
| Agriculture detection | WORKING — greenness index proxy |
| Change detection | WORKING — image differencing |
| Building detection | NOT CONFIGURED — requires Grounding DINO |
| BLIP captioning | NOT CONFIGURED — enable BLIP_ENABLED |
| BLIP VQA | NOT CONFIGURED — enable BLIP_VQA_ENABLED |
| BigEarthNet classification | NOT CONFIGURED — requires model weights |
| SAR fusion | NOT CONFIGURED — requires SAR model |
| Satellite imagery retrieval | NOT CONFIGURED — set SATELLITE_PROVIDER |
| Area calculation | REQUIRES GEOTIFF with CRS metadata |
| Water depth/level | UNAVAILABLE — requires hydrological data |
| Async jobs | REQUIRES REDIS — falls back to synchronous |

---

## License

This project is developed for research and educational purposes.
BigEarthNet dataset: https://bigearth.net/ (separate license)
OpenStreetMap: © OpenStreetMap contributors (ODbL)
