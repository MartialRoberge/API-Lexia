# Deployment Guide / Guide de Déploiement

[English](#english) | [Français](#français)

---

## English

### Prerequisites

- Docker Engine 24.0+
- Docker Compose 2.20+
- NVIDIA Container Toolkit (for GPU support)
- 32GB+ RAM recommended
- NVIDIA GPU with 16GB+ VRAM (A10, A100, or RTX 3090/4090)

### Infrastructure Requirements

| Component | CPU | RAM | GPU VRAM | Storage |
|-----------|-----|-----|----------|---------|
| API | 2 cores | 4GB | - | 10GB |
| vLLM (8B model) | 4 cores | 16GB | 16GB | 50GB |
| Whisper | 2 cores | 8GB | 8GB | 20GB |
| Worker | 2 cores | 4GB | - | 10GB |
| PostgreSQL | 2 cores | 4GB | - | 50GB |
| Redis | 1 core | 1GB | - | 2GB |

**Total minimum**: 13 cores, 37GB RAM, 24GB VRAM, 142GB storage

### Step-by-Step Deployment

#### 1. Clone and Configure

```bash
git clone <repository>
cd API-Lexia

# Create environment file
cp docker/.env.example docker/.env

# Edit configuration
nano docker/.env
```

#### 2. Essential Configuration

```env
# Security (CHANGE THESE!)
API_SECRET_KEY=your-very-long-random-secret-key-here
API_KEY_SALT=your-random-salt-here
POSTGRES_PASSWORD=your-secure-db-password

# Hugging Face (required for model access)
HF_TOKEN=hf_your_token_here

# Models
LLM_MODEL=Marsouuu/general7Bv2-ECE-PRYMMAL-Martial
WHISPER_MODEL=Gilbert-AI/gilbert-fr-source
DIARIZATION_MODEL=MEscriva/gilbert-pyannote-diarization

# Storage (for S3)
STORAGE_BACKEND=s3
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
S3_BUCKET_NAME=lexia-audio
S3_REGION=eu-west-1
```

#### 3. Build Images

```bash
# Build all images
docker compose -f docker/docker-compose.yml build

# Or build individually
docker build -f docker/Dockerfile.api -t lexia-api:latest .
docker build -f docker/Dockerfile.llm -t lexia-llm:latest .
docker build -f docker/Dockerfile.stt -t lexia-stt:latest .
docker build -f docker/Dockerfile.worker -t lexia-worker:latest .
```

#### 4. Start Services

```bash
# Start infrastructure first
docker compose -f docker/docker-compose.yml up -d postgres redis

# Wait for healthy status
docker compose -f docker/docker-compose.yml ps

# Start ML services (will download models)
docker compose -f docker/docker-compose.yml up -d llm stt

# Start API and workers
docker compose -f docker/docker-compose.yml up -d api worker beat
```

#### 5. Initialize Database

```bash
# Run migrations
docker compose -f docker/docker-compose.yml exec api \
  alembic upgrade head

# Create initial API key
docker compose -f docker/docker-compose.yml exec api \
  python -c "
from src.core.auth import APIKeyManager
from src.core.config import get_settings

settings = get_settings()
manager = APIKeyManager(settings)
key = manager.generate_api_key()
print(f'API Key: {key}')
print(f'Key Hash: {manager.hash_api_key(key)}')
"
```

#### 6. Verify Deployment

```bash
# Check health
curl http://localhost:8000/health

# Test LLM
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer lx_your_key" \
  -H "Content-Type: application/json" \
  -d '{"model": "general7Bv2", "messages": [{"role": "user", "content": "Test"}]}'

# Check logs
docker compose -f docker/docker-compose.yml logs -f api
```

### Scaling

#### Horizontal Scaling

```yaml
# docker-compose.override.yml
services:
  api:
    deploy:
      replicas: 3

  worker:
    deploy:
      replicas: 4
```

#### GPU Scaling (Multi-GPU)

```env
# For tensor parallelism across GPUs
TENSOR_PARALLEL=2
LLM_GPU_COUNT=2
```

### Monitoring

#### Prometheus Metrics

Add to docker-compose:

```yaml
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
```

#### Logs

```bash
# All logs
docker compose logs -f

# Specific service
docker compose logs -f api

# Export logs
docker compose logs api > api.log
```

### Backup & Recovery

#### PostgreSQL Backup

```bash
# Backup
docker compose exec postgres pg_dump -U lexia lexia > backup.sql

# Restore
docker compose exec -T postgres psql -U lexia lexia < backup.sql
```

#### S3/MinIO Backup

Use your cloud provider's backup tools or:

```bash
# With MinIO client
mc mirror minio/lexia-audio ./backup/
```

### Troubleshooting

#### Model Loading Fails

```bash
# Check GPU availability
docker compose exec llm nvidia-smi

# Check model download
docker compose logs llm | grep -i "model"
```

#### Memory Issues

```bash
# Reduce GPU memory usage
GPU_MEMORY_UTIL=0.7

# Or use smaller quantization
QUANTIZATION=awq
```

#### Connection Refused

```bash
# Check service health
docker compose ps

# Check internal DNS
docker compose exec api ping postgres
```

---

## Français

### Prérequis

- Docker Engine 24.0+
- Docker Compose 2.20+
- NVIDIA Container Toolkit (pour le support GPU)
- 32Go+ RAM recommandés
- GPU NVIDIA avec 16Go+ VRAM (A10, A100, ou RTX 3090/4090)

### Exigences Infrastructure

| Composant | CPU | RAM | GPU VRAM | Stockage |
|-----------|-----|-----|----------|----------|
| API | 2 cores | 4Go | - | 10Go |
| vLLM (modèle 8B) | 4 cores | 16Go | 16Go | 50Go |
| Whisper | 2 cores | 8Go | 8Go | 20Go |
| Worker | 2 cores | 4Go | - | 10Go |
| PostgreSQL | 2 cores | 4Go | - | 50Go |
| Redis | 1 core | 1Go | - | 2Go |

**Total minimum** : 13 cores, 37Go RAM, 24Go VRAM, 142Go stockage

### Déploiement étape par étape

#### 1. Cloner et Configurer

```bash
git clone <repository>
cd API-Lexia

# Créer le fichier d'environnement
cp docker/.env.example docker/.env

# Éditer la configuration
nano docker/.env
```

#### 2. Configuration Essentielle

```env
# Sécurité (CHANGEZ CES VALEURS!)
API_SECRET_KEY=votre-cle-secrete-tres-longue-et-aleatoire
API_KEY_SALT=votre-sel-aleatoire
POSTGRES_PASSWORD=votre-mot-de-passe-db-securise

# Hugging Face (requis pour l'accès aux modèles)
HF_TOKEN=hf_votre_token

# Modèles
LLM_MODEL=Marsouuu/general7Bv2-ECE-PRYMMAL-Martial
WHISPER_MODEL=Gilbert-AI/gilbert-fr-source
DIARIZATION_MODEL=MEscriva/gilbert-pyannote-diarization
```

#### 3. Démarrer les Services

```bash
# Démarrer l'infrastructure
docker compose -f docker/docker-compose.yml up -d postgres redis

# Démarrer les services ML
docker compose -f docker/docker-compose.yml up -d llm stt

# Démarrer l'API
docker compose -f docker/docker-compose.yml up -d api worker beat
```

### Déploiement Cloud

#### AWS (EC2 GPU)

Instance recommandée : `p3.2xlarge` ou `g4dn.xlarge`

```bash
# Installer Docker et NVIDIA Container Toolkit
sudo amazon-linux-extras install docker
sudo yum install -y nvidia-container-toolkit

# Déployer
docker compose -f docker/docker-compose.yml up -d
```

#### OVH Cloud

Instance recommandée : GPU Cloud avec NVIDIA T4 ou A100

```bash
# Déployer
docker compose -f docker/docker-compose.yml up -d
```

#### Outscale

Instance recommandée : Tinav5 avec GPU

```bash
# Déployer
docker compose -f docker/docker-compose.yml up -d
```

### Dépannage

#### Le modèle ne charge pas

```bash
# Vérifier la disponibilité GPU
docker compose exec llm nvidia-smi

# Vérifier les logs
docker compose logs llm
```

#### Problèmes de mémoire

```bash
# Réduire l'utilisation mémoire GPU
GPU_MEMORY_UTIL=0.7

# Ou utiliser une quantization plus petite
QUANTIZATION=awq
```

### Sauvegarde

```bash
# Sauvegarder PostgreSQL
docker compose exec postgres pg_dump -U lexia lexia > backup.sql

# Sauvegarder les fichiers audio (S3)
aws s3 sync s3://lexia-audio ./backup/
```
