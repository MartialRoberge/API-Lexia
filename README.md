# Lexia API

> Production-ready API for LLM inference, Speech-to-Text, and Speaker Diarization.

[English](#english) | [Français](#français)

---

## English

### Overview

Lexia API is a complete API solution for AI-powered audio processing and language model inference. Built with FastAPI, it provides:

- **LLM Inference**: Chat completion with vLLM backend, streaming, and tool calling
- **Speech-to-Text**: Audio transcription with Whisper (French-optimized)
- **Speaker Diarization**: Speaker separation with Pyannote

### Quick Start

#### Prerequisites

- Docker & Docker Compose
- NVIDIA GPU with CUDA 12.1+ (for production)
- Hugging Face token (for model access)

#### Development Mode (No GPU)

```bash
# Clone and navigate
cd API-Lexia

# Copy environment file
cp docker/.env.example docker/.env

# Start dev stack (with mocks)
docker compose -f docker/docker-compose.dev.yml up -d

# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/redoc
```

#### Production Mode (GPU)

```bash
# Configure environment
cp docker/.env.example docker/.env
# Edit .env with your settings (API keys, HF token, etc.)

# Start production stack
docker compose -f docker/docker-compose.yml up -d

# Check health
curl http://localhost:8000/health
```

### API Endpoints

#### LLM

```bash
# List models
curl -H "Authorization: Bearer lx_your_key" \
  http://localhost:8000/v1/models

# Chat completion
curl -X POST -H "Authorization: Bearer lx_your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "general7Bv2",
    "messages": [{"role": "user", "content": "Bonjour!"}]
  }' \
  http://localhost:8000/v1/chat/completions
```

#### Speech-to-Text

```bash
# Async transcription
curl -X POST -H "Authorization: Bearer lx_your_key" \
  -F "audio=@audio.wav" \
  -F "language_code=fr" \
  http://localhost:8000/v1/transcriptions

# Check status
curl -H "Authorization: Bearer lx_your_key" \
  http://localhost:8000/v1/transcriptions/{id}
```

#### Diarization

```bash
# Speaker diarization
curl -X POST -H "Authorization: Bearer lx_your_key" \
  -F "audio=@meeting.wav" \
  -F "num_speakers=3" \
  http://localhost:8000/v1/diarization
```

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Load Balancer                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Lexia API (FastAPI)                      │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌───────────────┐ │
│  │   LLM   │  │   STT   │  │ Diarize  │  │     Jobs      │ │
│  │ Router  │  │ Router  │  │  Router  │  │    Router     │ │
│  └────┬────┘  └────┬────┘  └────┬─────┘  └───────┬───────┘ │
└───────┼────────────┼────────────┼────────────────┼──────────┘
        │            │            │                │
        ▼            ▼            ▼                ▼
┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│   vLLM    │  │  Whisper  │  │ Pyannote  │  │  Celery   │
│  Server   │  │  Server   │  │  Server   │  │  Workers  │
│  (GPU)    │  │  (GPU)    │  │  (GPU)    │  │           │
└───────────┘  └───────────┘  └───────────┘  └─────┬─────┘
                                                    │
        ┌───────────────────────────────────────────┤
        ▼                                           ▼
┌───────────────┐                          ┌───────────────┐
│  PostgreSQL   │                          │     Redis     │
│  (Jobs, Keys) │                          │ (Queue/Cache) │
└───────────────┘                          └───────────────┘
        │
        ▼
┌───────────────┐
│    S3/MinIO   │
│    (Audio)    │
└───────────────┘
```

### Configuration

See `docker/.env.example` for all configuration options.

Key settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_MODEL` | Hugging Face model ID | `Marsouuu/general7Bv2-ECE-PRYMMAL-Martial` |
| `WHISPER_MODEL` | Whisper model ID | `Gilbert-AI/gilbert-fr-source` |
| `DIARIZATION_MODEL` | Pyannote model ID | `MEscriva/gilbert-pyannote-diarization` |
| `HF_TOKEN` | Hugging Face token | Required for private models |

### Model Quantization

For production, consider quantizing the LLM to AWQ/GPTQ format:

```bash
# Install AutoAWQ
pip install autoawq

# Quantize model
python -c "
from awq import AutoAWQForCausalLM
from transformers import AutoTokenizer

model = AutoAWQForCausalLM.from_pretrained('Marsouuu/general7Bv2-ECE-PRYMMAL-Martial')
tokenizer = AutoTokenizer.from_pretrained('Marsouuu/general7Bv2-ECE-PRYMMAL-Martial')

model.quantize(tokenizer, quant_config={'w_bit': 4, 'q_group_size': 128})
model.save_quantized('general7Bv2-awq')
"
```

---

## Français

### Présentation

Lexia API est une solution API complète pour le traitement audio par IA et l'inférence de modèles de langage. Construit avec FastAPI :

- **Inférence LLM** : Complétion de chat avec vLLM, streaming et appels de fonctions
- **Speech-to-Text** : Transcription audio avec Whisper (optimisé français)
- **Diarisation** : Séparation des locuteurs avec Pyannote

### Démarrage rapide

#### Prérequis

- Docker & Docker Compose
- GPU NVIDIA avec CUDA 12.1+ (pour la production)
- Token Hugging Face (pour l'accès aux modèles)

#### Mode Développement (Sans GPU)

```bash
# Cloner et naviguer
cd API-Lexia

# Copier le fichier d'environnement
cp docker/.env.example docker/.env

# Démarrer la stack dev (avec mocks)
docker compose -f docker/docker-compose.dev.yml up -d

# API disponible sur http://localhost:8000
# Documentation Swagger sur http://localhost:8000/redoc
```

#### Mode Production (GPU)

```bash
# Configurer l'environnement
cp docker/.env.example docker/.env
# Éditer .env avec vos paramètres (clés API, token HF, etc.)

# Démarrer la stack production
docker compose -f docker/docker-compose.yml up -d

# Vérifier la santé
curl http://localhost:8000/health
```

### Endpoints API

#### LLM

```bash
# Lister les modèles
curl -H "Authorization: Bearer lx_votre_cle" \
  http://localhost:8000/v1/models

# Complétion de chat
curl -X POST -H "Authorization: Bearer lx_votre_cle" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "general7Bv2",
    "messages": [{"role": "user", "content": "Bonjour!"}]
  }' \
  http://localhost:8000/v1/chat/completions
```

#### Speech-to-Text

```bash
# Transcription asynchrone
curl -X POST -H "Authorization: Bearer lx_votre_cle" \
  -F "audio=@audio.wav" \
  -F "language_code=fr" \
  http://localhost:8000/v1/transcriptions

# Vérifier le statut
curl -H "Authorization: Bearer lx_votre_cle" \
  http://localhost:8000/v1/transcriptions/{id}
```

### Déploiement Cloud

#### AWS

```bash
# Avec EC2 GPU (p3.2xlarge ou g4dn.xlarge)
docker compose -f docker/docker-compose.yml up -d
```

#### OVH Cloud

```bash
# Avec GPU Cloud
docker compose -f docker/docker-compose.yml up -d
```

#### Outscale

```bash
# Instance GPU Tinav5
docker compose -f docker/docker-compose.yml up -d
```

### Tests

```bash
# Tests unitaires
pytest tests/ -v

# Tests d'intégration (nécessite stack en cours)
pytest tests/integration/ -v
```

### Compatibilité LiteLLM

Pour utiliser Lexia API avec LiteLLM comme provider custom :

```python
import litellm

# Configurer le provider
litellm.register_model({
    "model_name": "lexia/general7Bv2",
    "litellm_provider": "openai",
    "model_info": {
        "api_base": "http://your-lexia-api:8000/v1",
        "api_key": "lx_your_key",
    }
})

# Utiliser
response = litellm.completion(
    model="lexia/general7Bv2",
    messages=[{"role": "user", "content": "Bonjour!"}]
)
```

### Licence

MIT License - Voir LICENSE pour plus de détails.

### Contact

- Site : https://gilbert-assistant.fr
- Email : contact@lexia.fr
