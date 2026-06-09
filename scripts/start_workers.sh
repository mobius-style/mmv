#!/bin/bash
# start_workers.sh — Wall-ball workers via Ollama API
#
# Design:
#   Ollama handles GPU scheduling internally.
#   qwen3.5:4b is used via Ollama /api/generate (parallel capable).
#   No llama-server needed (qwen3.5 GGUF has rope compatibility issues).
#
# Usage:
#   bash scripts/start_workers.sh

echo "=== MOBIUS Wall-Ball Worker Check ==="
echo ""

# Check Ollama is running
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[OK] Ollama is running"
else
    echo "[ERROR] Ollama is not running. Start with: ollama serve"
    exit 1
fi

# Check qwen3.5:4b is available
if ollama list 2>/dev/null | grep -q "qwen3.5:4b"; then
    echo "[OK] qwen3.5:4b is available"
else
    echo "[WARN] qwen3.5:4b not found. Pulling..."
    ollama pull qwen3.5:4b
fi

# Warmup — load model into GPU
echo ""
echo "Warming up qwen3.5:4b..."
curl -s http://localhost:11434/api/generate \
    -d '{"model":"qwen3.5:4b","prompt":"ping","stream":false,"think":false,"options":{"num_predict":1}}' \
    > /dev/null 2>&1
echo "[OK] Model loaded"

# VRAM check
echo ""
nvidia-smi --query-gpu=index,name,memory.used,memory.free \
    --format=csv,noheader 2>/dev/null || echo "[WARN] nvidia-smi not available"

echo ""
echo "=== Workers Ready ==="
echo "  Ollama API: http://localhost:11434/api/generate"
echo "  Model:      qwen3.5:4b"
echo "  Parallel:   Ollama handles concurrent requests"
echo ""
echo "Run wall-ball:"
echo "  python scripts/wall_ball_generator.py --probe"
echo "  python scripts/wall_ball_generator.py --turns 500"
