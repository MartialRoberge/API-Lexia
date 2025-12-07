#!/bin/bash
# =============================================================================
# Lexia LLM Server - Entrypoint Script
# =============================================================================
set -e

echo "=============================================="
echo "  Lexia LLM Server - Starting vLLM"
echo "=============================================="
echo "Model: ${MODEL_NAME}"
echo "Max Length: ${MAX_MODEL_LEN}"
echo "GPU Memory Utilization: ${GPU_MEMORY_UTILIZATION}"
echo "=============================================="

# Wait for model download if needed
if [ ! -z "${HF_TOKEN}" ]; then
    echo "Hugging Face token detected, configuring authentication..."
    huggingface-cli login --token "${HF_TOKEN}" --add-to-git-credential 2>/dev/null || true
fi

# Build vLLM command with optional parameters
VLLM_ARGS=(
    "--model" "${MODEL_NAME}"
    "--host" "${VLLM_HOST:-0.0.0.0}"
    "--port" "${VLLM_PORT:-8001}"
    "--dtype" "${MODEL_DTYPE:-auto}"
    "--max-model-len" "${MAX_MODEL_LEN:-4096}"
    "--gpu-memory-utilization" "${GPU_MEMORY_UTILIZATION:-0.9}"
)

# Add tensor parallelism if specified
if [ ! -z "${TENSOR_PARALLEL_SIZE}" ] && [ "${TENSOR_PARALLEL_SIZE}" != "1" ]; then
    VLLM_ARGS+=("--tensor-parallel-size" "${TENSOR_PARALLEL_SIZE}")
fi

# Add quantization if specified
if [ ! -z "${QUANTIZATION}" ]; then
    VLLM_ARGS+=("--quantization" "${QUANTIZATION}")
fi

# Add trust remote code if needed
if [ "${TRUST_REMOTE_CODE:-false}" = "true" ]; then
    VLLM_ARGS+=("--trust-remote-code")
fi

# Add download directory
if [ ! -z "${HF_HOME}" ]; then
    VLLM_ARGS+=("--download-dir" "${HF_HOME}")
fi

echo "Starting vLLM with arguments: ${VLLM_ARGS[*]}"

# Start vLLM server
exec python -m vllm.entrypoints.openai.api_server "${VLLM_ARGS[@]}"
