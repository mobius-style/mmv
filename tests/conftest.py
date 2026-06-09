"""Pytest session configuration.

Default ME5 embeddings to CPU during tests. The GPU on the dev/CI box is
typically occupied by Ollama (~8 GiB) while the suite instantiates many ME5
encoders across modules, so GPU test runs intermittently hit CUDA OOM. CPU
embedding makes the suite reproducibly green regardless of GPU contention.

To run the suite on GPU (e.g. with Ollama stopped), set the env var explicitly:
    MMV_EMBEDDING_DEVICE=cuda python -m pytest tests/
"""
import os

# setdefault: only forces CPU when the caller has not chosen a device.
os.environ.setdefault("MMV_EMBEDDING_DEVICE", "cpu")
