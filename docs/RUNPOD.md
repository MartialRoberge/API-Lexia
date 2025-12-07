---
layout: default
title: RunPod Deployment
---

# RunPod Deployment Guide

Deploy Lexia API on RunPod GPU cloud.

## Prerequisites

- RunPod account with credits
- Hugging Face token (for model access)
- GPU with 24GB+ VRAM (A40, A100 recommended)

## Quick Start

### 1. Create Pod on RunPod

1. Go to [runpod.io](https://runpod.io) > Deploy > GPU Pods
2. Select template: **RunPod Pytorch 2.1.0**
3. Choose GPU: **A40** (46GB) or **A100** (40/80GB)
4. Configure:
   - Container Disk: 50GB
   - Volume Disk: 100GB
   - Volume mount path: `/workspace`
   - Expose HTTP ports: `8000`
5. Click **Deploy**

### 2. Initial Setup

Connect via Web Terminal and run:

```bash
# Install dependencies
apt-get update
apt-get install -y python3-pip python3-venv postgresql redis-server ffmpeg libsndfile1 git

# Clone repository
cd /workspace
git clone https://github.com/MartialRoberge/API-Lexia.git
cd API-Lexia

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install --upgrade pip wheel setuptools
pip install torch==2.1.0 torchaudio==2.1.0 --index-url https://download.pytorch.org/whl/cu118
pip install "numpy<2"
pip install vllm transformers accelerate safetensors sentencepiece tokenizers
pip install faster-whisper ctranslate2 pyannote.audio speechbrain
pip install -r requirements.txt
```

### 3. Configure PostgreSQL

```bash
# Start PostgreSQL
service postgresql start

# Configure authentication (run as one block)
cat > /etc/postgresql/14/main/pg_hba.conf << 'EOF'
local   all             postgres                                peer
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
host    all             all             0.0.0.0/0               trust
EOF

# Restart PostgreSQL
service postgresql restart

# Create database
su - postgres -c "psql -c \"CREATE USER lexia WITH PASSWORD 'lexia123' SUPERUSER;\""
su - postgres -c "psql -c \"CREATE DATABASE lexia OWNER lexia;\""
```

### 4. Configure Environment

```bash
# Create .env file
cat > /workspace/API-Lexia/.env << 'EOF'
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
API_SECRET_KEY=your-secret-key-minimum-32-characters-here
API_KEY_SALT=your-salt-16-chars
DATABASE_URL=postgresql+asyncpg://lexia:lexia123@localhost:5432/lexia
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
LLM_SERVICE_URL=http://localhost:8005
STT_SERVICE_URL=http://localhost:8002
HF_TOKEN=hf_your_huggingface_token_here
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=/workspace/API-Lexia/data
USE_MOCK_LLM=false
USE_MOCK_STT=false
USE_MOCK_DIARIZATION=false
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60
LOG_LEVEL=INFO
EOF

# Create data directory
mkdir -p /workspace/API-Lexia/data
```

### 5. Initialize Database

```bash
cd /workspace/API-Lexia
source venv/bin/activate
export PYTHONPATH=/workspace/API-Lexia
alembic upgrade head
```

### 6. Create API Key

```bash
# Generate hash for API key
python3 << 'EOF'
import hashlib
salt = "your-salt-16-chars"  # Must match API_KEY_SALT in .env
api_key = "lx_your_secure_api_key_here_min_40_chars"
key_body = api_key[3:]  # Remove "lx_" prefix
key_hash = hashlib.sha256((salt + key_body).encode()).hexdigest()
print(f"API Key: {api_key}")
print(f"Hash: {key_hash}")
EOF

# Insert into database (replace HASH with output from above)
su - postgres -c "psql -d lexia -c \"INSERT INTO api_keys (id, key_hash, name, user_id, permissions, rate_limit, is_revoked, created_at, updated_at) VALUES (gen_random_uuid(), 'YOUR_HASH_HERE', 'Production Key', 'user-1', '[\\\"*\\\"]', 60, false, now(), now());\""
```

### 7. Create Startup Script

```bash
cat > /workspace/start.sh << 'EOF'
#!/bin/bash
set -e

echo "Starting Lexia API..."

# Start services
service postgresql start
service redis-server start
sleep 2

# Activate environment
cd /workspace/API-Lexia
source venv/bin/activate
export PYTHONPATH=/workspace/API-Lexia
export DATABASE_URL="postgresql+asyncpg://lexia:lexia123@localhost:5432/lexia"
export REDIS_URL="redis://localhost:6379/0"
export API_SECRET_KEY="your-secret-key-minimum-32-characters-here"
export API_KEY_SALT="your-salt-16-chars"
export LLM_SERVICE_URL="http://localhost:8005"
export STORAGE_BACKEND="local"
export LOCAL_STORAGE_PATH="/workspace/API-Lexia/data"
export HF_TOKEN="hf_your_huggingface_token_here"

# Start API in background
echo "Starting FastAPI..."
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &
sleep 5

# Start vLLM
echo "Starting vLLM (this may take a few minutes)..."
python -m vllm.entrypoints.openai.api_server \
  --model Marsouuu/general7Bv2-ECE-PRYMMAL-Martial \
  --port 8005

EOF
chmod +x /workspace/start.sh
```

### 8. Start Services

```bash
/workspace/start.sh
```

Wait for vLLM to show `Application startup complete`.

### 9. Test API

```bash
# Health check
curl http://localhost:8000/health

# Chat completion
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer lx_your_secure_api_key_here_min_40_chars" \
  -H "Content-Type: application/json" \
  -d '{"model":"general7Bv2","messages":[{"role":"user","content":"Bonjour!"}]}'
```

## External Access

Your API is accessible at:
```
https://<pod-id>-8000.proxy.runpod.net
```

Find the URL in RunPod > Your Pod > Connect > HTTP Services.

## Troubleshooting

### GPU Memory Error

If vLLM fails with "Free memory less than desired":
```bash
# Kill all Python processes
pkill -9 -f python
sleep 3

# Restart with lower memory utilization
python -m vllm.entrypoints.openai.api_server \
  --model Marsouuu/general7Bv2-ECE-PRYMMAL-Martial \
  --port 8005 \
  --gpu-memory-utilization 0.7
```

Or restart the pod from RunPod interface.

### Database Connection Error

```bash
# Restart PostgreSQL
service postgresql restart

# Check connection
PGPASSWORD=lexia123 psql -U lexia -d lexia -h localhost -c "SELECT 1;"
```

### Port Already in Use

```bash
# Find and kill process
apt-get install -y psmisc
fuser -k 8000/tcp
fuser -k 8005/tcp
```

## Service Status

| Service | Port | Command to Check |
|---------|------|------------------|
| API | 8000 | `curl localhost:8000/health` |
| vLLM | 8005 | `curl localhost:8005/health` |
| PostgreSQL | 5432 | `service postgresql status` |
| Redis | 6379 | `service redis-server status` |

## Costs

| GPU | VRAM | Price/hour | Recommendation |
|-----|------|------------|----------------|
| A40 | 46GB | ~$0.79/h | Best value |
| A100 40GB | 40GB | ~$1.50/h | Production |
| A100 80GB | 80GB | ~$2.00/h | High load |

## Network Volume

To persist data and models between restarts:
1. Create a Network Volume in RunPod (100GB)
2. Attach to pod at `/workspace`
3. Models are cached in `~/.cache/huggingface`
