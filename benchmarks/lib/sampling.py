"""Deterministic sampling helpers used by runners.

Slicing benchmark datasets must be reproducible across runs and across model
profiles — otherwise 9B vs 120B scores are not directly comparable.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, TypeVar

T = TypeVar("T")


def stable_sample(items: list[T], n: int, seed: str = "mobius-mmv") -> list[T]:
    """Pick the first n items in a stable, seed-derived order.

    We order by sha256(seed + index) to avoid the bias of always taking the
    head of the dataset, then take the first n. Deterministic given (n, seed,
    len(items), order of items).
    """
    if n <= 0 or not items:
        return []
    if n >= len(items):
        return list(items)
    keyed = [
        (hashlib.sha256(f"{seed}:{i}".encode()).digest(), i, x)
        for i, x in enumerate(items)
    ]
    keyed.sort(key=lambda t: t[0])
    return [t[2] for t in keyed[:n]]


def head(items: Iterable[T], n: int) -> list[T]:
    out: list[T] = []
    for i, x in enumerate(items):
        if i >= n:
            break
        out.append(x)
    return out
