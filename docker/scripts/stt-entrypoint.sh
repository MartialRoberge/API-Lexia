#!/bin/bash
# =============================================================================
# Lexia STT Server - Entrypoint Script
# =============================================================================
set -e

echo "=============================================="
echo "  Lexia STT Server - Starting"
echo "=============================================="
echo "Whisper Model: ${WHISPER_MODEL}"
echo "Diarization Model: ${DIARIZATION_MODEL}"
echo "Device: ${DEVICE}"
echo "Compute Type: ${COMPUTE_TYPE}"
echo "=============================================="

# Configure Hugging Face authentication
if [ ! -z "${HF_TOKEN}" ]; then
    echo "Hugging Face token detected, configuring authentication..."
    huggingface-cli login --token "${HF_TOKEN}" --add-to-git-credential 2>/dev/null || true
fi

# Pre-download models if not cached
echo "Checking model cache..."

# Download Whisper model
python -c "
from faster_whisper import WhisperModel
import os

model_name = os.environ.get('WHISPER_MODEL', 'Gilbert-AI/gilbert-fr-source')
device = os.environ.get('DEVICE', 'cuda')
compute_type = os.environ.get('COMPUTE_TYPE', 'float16')

print(f'Loading Whisper model: {model_name}')
try:
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    print('Whisper model loaded successfully')
except Exception as e:
    print(f'Warning: Could not pre-load Whisper model: {e}')
"

# Download Diarization model
python -c "
from pyannote.audio import Pipeline
import os
import torch

model_name = os.environ.get('DIARIZATION_MODEL', 'MEscriva/gilbert-pyannote-diarization')
hf_token = os.environ.get('HF_TOKEN', '')

print(f'Loading Diarization model: {model_name}')
try:
    pipeline = Pipeline.from_pretrained(model_name, use_auth_token=hf_token if hf_token else None)
    if torch.cuda.is_available():
        pipeline.to(torch.device('cuda'))
    print('Diarization model loaded successfully')
except Exception as e:
    print(f'Warning: Could not pre-load Diarization model: {e}')
"

echo "Starting STT server..."

# Start the STT FastAPI server
exec uvicorn src.services.stt.server:app \
    --host "${STT_HOST:-0.0.0.0}" \
    --port "${STT_PORT:-8002}" \
    --workers 1
