# Production Checklist / Liste de Vérification Production

## Pre-Deployment / Avant Déploiement

### 1. Security / Sécurité

- [ ] **Secrets Management / Gestion des secrets**
  - [ ] All secrets in environment variables (not in code)
  - [ ] `.env` file excluded from git
  - [ ] Strong API_SECRET_KEY (32+ chars, random)
  - [ ] Strong API_KEY_SALT (16+ chars, random)
  - [ ] HF_TOKEN valid and not expired

- [ ] **Authentication / Authentification**
  - [ ] API key authentication working
  - [ ] Rate limiting configured
  - [ ] Invalid auth returns 401

- [ ] **Network / Réseau**
  - [ ] HTTPS enabled (behind reverse proxy)
  - [ ] CORS configured for your domains only
  - [ ] Internal services not exposed publicly (LLM, STT, Redis, Postgres)

### 2. Database / Base de Données

- [ ] **PostgreSQL**
  - [ ] Strong password set
  - [ ] Connection pooling configured
  - [ ] Backups configured
  - [ ] Alembic migrations applied

- [ ] **Redis**
  - [ ] Password set (if exposed)
  - [ ] Memory limits configured
  - [ ] Persistence configured (if needed)

### 3. Infrastructure

- [ ] **Docker**
  - [ ] Images built with production tags
  - [ ] Resource limits set (memory, CPU)
  - [ ] Health checks configured
  - [ ] Restart policies set

- [ ] **GPU (Production)**
  - [ ] NVIDIA drivers installed
  - [ ] nvidia-container-toolkit installed
  - [ ] GPU memory limits set
  - [ ] Models downloaded and cached

- [ ] **Storage**
  - [ ] S3/MinIO configured for production
  - [ ] Bucket permissions set correctly
  - [ ] Lifecycle policies configured

### 4. Monitoring / Surveillance

- [ ] **Logging**
  - [ ] Structured logging enabled
  - [ ] Log aggregation configured (ELK, CloudWatch, etc.)
  - [ ] Log retention policy set

- [ ] **Metrics**
  - [ ] Prometheus metrics exposed (optional)
  - [ ] Alerting configured

- [ ] **Health Checks**
  - [ ] /health endpoint monitored
  - [ ] Automated alerts on degraded status

### 5. Performance / Performances

- [ ] **Load Testing**
  - [ ] Tested with expected user load
  - [ ] Tested with 2x expected load
  - [ ] Response times acceptable (<500ms for chat)

- [ ] **Scaling**
  - [ ] Horizontal scaling tested
  - [ ] Worker concurrency tuned

### 6. Code Quality / Qualité du Code

- [ ] **Tests**
  - [ ] All unit tests passing
  - [ ] Integration tests passing
  - [ ] Coverage > 70%

- [ ] **Static Analysis**
  - [ ] No Bandit security issues (high/medium)
  - [ ] No vulnerable dependencies
  - [ ] Type checking passes

### 7. Documentation

- [ ] **API**
  - [ ] OpenAPI schema complete
  - [ ] All endpoints documented
  - [ ] Error responses documented

- [ ] **Operations**
  - [ ] Deployment guide complete
  - [ ] Runbook for common issues
  - [ ] Contact info for support

---

## Commands / Commandes

### Run Full Audit / Lancer l'Audit Complet
```bash
./scripts/audit.sh
```

### Run Tests / Lancer les Tests
```bash
# Local
pip install -r requirements-dev.txt
pytest tests/ -v --cov=src

# Docker
docker compose -f docker/docker-compose.test.yml run --rm test
```

### Security Scan / Scan de Sécurité
```bash
# Bandit
bandit -r src/ -ll

# Dependency vulnerabilities
pip-audit --strict

# Docker
docker compose -f docker/docker-compose.test.yml run --rm security
```

### Type Check / Vérification des Types
```bash
mypy src/ --ignore-missing-imports --strict
```

### Load Test / Test de Charge
```bash
# Install Locust
pip install locust

# Run (then open http://localhost:8089)
locust -f tests/load/locustfile.py --host=http://localhost:8000
```

### Test Endpoints Manually / Tester les Endpoints
```bash
./scripts/test_endpoints.sh http://localhost:8000 your-api-key
```

---

## Production Environment Variables / Variables d'Environnement Production

```env
# General
APP_ENV=production
APP_DEBUG=false

# Security (CHANGE THESE!)
API_SECRET_KEY=<generate-32-char-random-string>
API_KEY_SALT=<generate-16-char-random-string>

# Database
POSTGRES_USER=lexia
POSTGRES_PASSWORD=<strong-random-password>
POSTGRES_DB=lexia
DATABASE_URL=postgresql+asyncpg://lexia:<password>@postgres:5432/lexia

# Redis
REDIS_URL=redis://:password@redis:6379/0

# LLM
LLM_MODEL=Marsouuu/general7Bv2-ECE-PRYMMAL-Martial
GPU_MEMORY_UTIL=0.9

# STT
WHISPER_MODEL=Gilbert-AI/gilbert-fr-source
DIARIZATION_MODEL=MEscriva/gilbert-pyannote-diarization

# HuggingFace
HF_TOKEN=<your-hf-token>

# Storage
STORAGE_BACKEND=s3
S3_BUCKET=lexia-audio
S3_ENDPOINT=https://s3.amazonaws.com
AWS_ACCESS_KEY_ID=<access-key>
AWS_SECRET_ACCESS_KEY=<secret-key>
```

---

## Deployment Steps / Étapes de Déploiement

1. **Clone repository** on production server
2. **Create `.env`** file with production values
3. **Pull/build images**:
   ```bash
   docker compose pull
   docker compose build
   ```
4. **Run database migrations**:
   ```bash
   docker compose run --rm api alembic upgrade head
   ```
5. **Start services**:
   ```bash
   docker compose up -d
   ```
6. **Verify health**:
   ```bash
   curl https://your-api.com/health
   ```
7. **Create initial API key** in database
8. **Test endpoints** with real API key

---

## Rollback / Retour en Arrière

If something goes wrong:

```bash
# Stop services
docker compose down

# Revert to previous version
git checkout <previous-commit>

# Rebuild and restart
docker compose build
docker compose up -d

# Revert database (if needed)
docker compose run --rm api alembic downgrade -1
```
