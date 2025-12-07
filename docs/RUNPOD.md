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
# Install system dependencies
apt-get update
apt-get install -y python3-pip python3-venv postgresql redis-server ffmpeg libsndfile1 git

# Install cuDNN 8 (required for faster-whisper with CUDA)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb
dpkg -i cuda-keyring_1.0-1_all.deb
apt-get update
apt-get install -y libcudnn8

# Clone repository
cd /workspace
git clone https://github.com/MartialRoberge/API-Lexia.git
cd API-Lexia

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install --upgrade pip wheel setuptools

# Install PyTorch 2.9 (required for vLLM)
pip install torch==2.9.0 torchvision==0.24.0 torchaudio==2.9.0

# Install vLLM
pip install vllm

# Install faster-whisper with compatible ctranslate2 (for CUDA support)
pip install faster-whisper ctranslate2==4.4.0

# Install other dependencies
pip install "numpy<2"
pip install transformers accelerate safetensors sentencepiece tokenizers
pip install librosa soundfile httpx

# Install project requirements
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

echo "=========================================="
echo "  Starting Lexia API - All Services"
echo "=========================================="

# Start system services
echo "[1/5] Starting PostgreSQL and Redis..."
service postgresql start
service redis-server start
sleep 2

# Activate environment
cd /workspace/API-Lexia
source venv/bin/activate

# Export all environment variables
export PYTHONPATH=/workspace/API-Lexia
export DATABASE_URL="postgresql+asyncpg://lexia:lexia123@localhost:5432/lexia"
export REDIS_URL="redis://localhost:6379/0"
export API_SECRET_KEY="your-secret-key-minimum-32-characters-here"
export API_KEY_SALT="your-salt-16-chars"
export LLM_SERVICE_URL="http://localhost:8005"
export STT_SERVICE_URL="http://localhost:8002"
export STORAGE_BACKEND="local"
export LOCAL_STORAGE_PATH="/workspace/API-Lexia/data"
export HF_TOKEN="hf_your_huggingface_token_here"

# STT Configuration (faster-whisper with CUDA)
export USE_TRANSFORMERS=false
export WHISPER_MODEL="large-v3"
export DEVICE=cuda

# Start STT server in background (uses ~3GB GPU)
echo "[2/5] Starting STT server (Whisper large-v3)..."
python -m uvicorn src.services.stt.server:app --host 0.0.0.0 --port 8002 &
STT_PID=$!
sleep 15  # Wait for Whisper model to load

# Verify STT is running
if curl -s http://localhost:8002/health > /dev/null; then
    echo "  ✓ STT server started successfully"
else
    echo "  ✗ STT server failed to start"
fi

# Start API Gateway in background
echo "[3/5] Starting API Gateway..."
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!
sleep 5

# Verify API is running
if curl -s http://localhost:8000/health > /dev/null; then
    echo "  ✓ API Gateway started successfully"
else
    echo "  ✗ API Gateway failed to start"
fi

# Start vLLM (foreground, uses ~20GB GPU)
echo "[4/5] Starting vLLM (this takes 2-3 minutes)..."
echo "  Model: Marsouuu/general7Bv2-ECE-PRYMMAL-Martial"
echo "  GPU Memory: 50%"

python -m vllm.entrypoints.openai.api_server \
  --model Marsouuu/general7Bv2-ECE-PRYMMAL-Martial \
  --port 8005 \
  --gpu-memory-utilization 0.5

EOF
chmod +x /workspace/start.sh
```

> **Note**: Diarization is currently disabled due to torch version conflicts with vLLM.
> It will be re-enabled when pyannote-audio supports torch 2.9.

### 8. Start Services

```bash
/workspace/start.sh
```

Wait for vLLM to show `Application startup complete`.

### 9. Test All Services

```bash
# Health checks
curl http://localhost:8000/health   # API Gateway
curl http://localhost:8002/health   # STT Server
curl http://localhost:8005/health   # vLLM

# Test LLM (Chat completion)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer lx_your_secure_api_key_here_min_40_chars" \
  -H "Content-Type: application/json" \
  -d '{"model":"general7Bv2","messages":[{"role":"user","content":"Bonjour!"}]}'

# Test STT directly (without API Gateway)
curl -X POST http://localhost:8002/transcribe \
  -F "audio=@/path/to/audio.wav"

# Test STT via API Gateway
curl -X POST http://localhost:8000/v1/transcriptions/sync \
  -H "Authorization: Bearer lx_your_secure_api_key_here_min_40_chars" \
  -F "audio=@/path/to/audio.wav" \
  -F "language_code=fr"
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
fuser -k 8002/tcp
fuser -k 8005/tcp
```

## Service Status

| Service | Port | Command to Check |
|---------|------|------------------|
| API | 8000 | `curl localhost:8000/health` |
| STT/Diarization | 8002 | `curl localhost:8002/health` |
| vLLM | 8005 | `curl localhost:8005/health` |
| PostgreSQL | 5432 | `service postgresql status` |
| Redis | 6379 | `service redis-server status` |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    RunPod Single Pod                        │
│                      A40 (46GB)                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐                                      │
│  │   API Gateway    │  Port 8000                           │
│  │    (FastAPI)     │  Stateless, no GPU                   │
│  └────────┬─────────┘                                      │
│           │                                                 │
│     ┌─────┴─────┐                                          │
│     ▼           ▼                                           │
│  ┌──────────┐  ┌──────────────────┐                        │
│  │   vLLM   │  │   STT Server     │                        │
│  │  :8005   │  │     :8002        │                        │
│  │  ~20GB   │  │     ~3GB         │                        │
│  │  7B LLM  │  │  Whisper v3      │                        │
│  └──────────┘  └──────────────────┘                        │
│                                                             │
│  GPU Memory: ~23GB / 46GB available                        │
│                                                             │
│  Tech Stack:                                               │
│  - vLLM 0.12 + torch 2.9.0                                │
│  - faster-whisper + ctranslate2 4.4.0                     │
│  - cuDNN 8 (libcudnn8)                                    │
└─────────────────────────────────────────────────────────────┘
```

## Scaling (Production)

For production with multiple GPUs/pods:

```bash
# Pod 1: API Gateway (no GPU)
STT_SERVICE_URL=http://stt-pod:8002
LLM_SERVICE_URL=http://llm-pod:8005

# Pod 2: LLM only (GPU)
python -m vllm.entrypoints.openai.api_server --port 8005

# Pod 3: STT/Diarization only (GPU)
python -m uvicorn src.services.stt.server:app --port 8002
```

Each service can be scaled independently behind a load balancer.

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
