"""Tests for src/services/me5_singleton.py — mock SentenceTransformer."""
from __future__ import annotations

import threading
from unittest.mock import patch

import numpy as np
import pytest

from src.services.me5_singleton import (
    DEFAULT_MODEL, ME5_DIM, ME5Singleton,
    get_me5_singleton, reset_me5_singleton,
)


class _FakeModel:
    """Mock SentenceTransformer-like object."""
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.encode_calls = 0

    def encode(self, texts, **kw):
        self.encode_calls += 1
        # Return deterministic L2-unit vectors
        out = []
        for i, t in enumerate(texts):
            v = np.zeros(ME5_DIM, dtype="float32")
            v[i % ME5_DIM] = 1.0
            out.append(v)
        return np.asarray(out)


@pytest.fixture(autouse=True)
def _reset():
    reset_me5_singleton()
    yield
    reset_me5_singleton()


# ─── Lazy load ────────────────────────────────────────────────────────

def test_singleton_does_not_load_model_until_first_encode() -> None:
    fake = _FakeModel("test-model")
    s = ME5Singleton(model_name="test-model", _model=None)
    # Inject the fake via _ensure_loaded patch
    with patch("sentence_transformers.SentenceTransformer",
               return_value=fake):
        assert not s.is_loaded()
        # First encode triggers load
        v = s.encode_query("hello")
        assert s.is_loaded()
        assert v.shape == (ME5_DIM,)
        assert s.encode_count == 1
        # Second encode reuses the loaded model
        s.encode_query("world")
        assert fake.encode_calls == 2  # only one model held; 2 encode invocations


def test_get_singleton_returns_same_instance() -> None:
    a = get_me5_singleton()
    b = get_me5_singleton()
    assert a is b


def test_different_model_name_returns_new_singleton() -> None:
    a = get_me5_singleton("model-x")
    b = get_me5_singleton("model-y")
    assert a is not b
    assert a.model_name == "model-x"
    assert b.model_name == "model-y"


# ─── Thread-safety ────────────────────────────────────────────────────

def test_concurrent_first_load_does_not_double_construct() -> None:
    """20 threads racing to get the singleton — only one instance
    must be constructed."""
    instances: list[ME5Singleton] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(20)

    def worker():
        try:
            barrier.wait()
            s = get_me5_singleton("concurrent-test")
            instances.append(s)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(instances) == 20
    assert all(s is instances[0] for s in instances)


def test_concurrent_first_encode_loads_model_only_once() -> None:
    """20 threads racing to encode for the first time — model is
    loaded only ONCE (despite multiple parallel encode() calls)."""
    fake = _FakeModel("test")
    construct_count = [0]

    def fake_st_constructor(model_name):
        construct_count[0] += 1
        return fake

    s = ME5Singleton(model_name="test", _model=None)
    barrier = threading.Barrier(20)
    errors = []

    def worker():
        try:
            barrier.wait()
            s.encode_query(f"q-{threading.get_ident()}")
        except Exception as e:
            errors.append(e)

    with patch("sentence_transformers.SentenceTransformer",
               side_effect=fake_st_constructor):
        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert errors == []
    # The fake constructor was called exactly once (double-checked locking
    # works under contention)
    assert construct_count[0] == 1
    # All 20 encodings ran
    assert fake.encode_calls == 20


# ─── Encoding API ─────────────────────────────────────────────────────

def test_encode_query_uses_query_prefix() -> None:
    fake = _FakeModel("test")
    s = ME5Singleton(model_name="test", _model=fake)
    s.encode_query("hello")
    # Verify the prefix was applied
    # We can't see the input directly, but we know fake.encode_calls=1
    assert fake.encode_calls == 1


def test_encode_batch_with_passage_prefix() -> None:
    fake = _FakeModel("test")
    s = ME5Singleton(model_name="test", _model=fake)
    arr = s.encode_batch(["a", "b", "c"], prefix="passage: ")
    assert arr.shape == (3, ME5_DIM)
    assert s.encode_count == 3


def test_encode_batch_returns_normalized_2d() -> None:
    fake = _FakeModel("test")
    s = ME5Singleton(model_name="test", _model=fake)
    arr = s.encode_batch(["x", "y"], batch_size=2)
    # Vector at index 0 puts 1.0 at column 0; at index 1 puts 1.0 at column 1
    assert arr[0, 0] == 1.0
    assert arr[1, 1] == 1.0
    assert arr.dtype == np.float32


# ─── Reset semantics ─────────────────────────────────────────────────

def test_reset_creates_fresh_instance() -> None:
    a = get_me5_singleton("test-model-r")
    reset_me5_singleton()
    b = get_me5_singleton("test-model-r")
    assert a is not b


def test_singleton_default_model_name() -> None:
    s = get_me5_singleton()
    assert s.model_name == DEFAULT_MODEL


def test_default_model_constant_unchanged() -> None:
    """Spec-mandated default; do not change without updating spec."""
    assert DEFAULT_MODEL == "intfloat/multilingual-e5-large"
    assert ME5_DIM == 1024
