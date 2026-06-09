"""Phase 1 — stratified sampling of 4 frontier benchmarks (seed=42).

Outputs one CSV per bench under <outdir>/datasets/sampled_<bench>.csv with
columns: question_id, subject_or_category, question, options (json), expected.

Each row's `question_id` is stable (bench_<index>_<short_hash>) so re-runs
hit the same questions.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset


SEED = 42


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _stratified_pick(
    rows: list[dict],
    key_fn,
    total: int,
    rng: random.Random,
) -> list[dict]:
    """Stratify by key_fn(row); split `total` evenly across strata.

    Distributes any remainder by sampling extra rows from larger strata first.
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[key_fn(r)].append(r)

    strata = sorted(buckets.keys())
    base = total // len(strata)
    remainder = total - base * len(strata)

    sized = []
    for s in strata:
        sized.append((s, base + (1 if remainder > 0 else 0)))
        if remainder > 0:
            remainder -= 1

    picked: list[dict] = []
    for s, n in sized:
        items = buckets[s]
        if len(items) <= n:
            picked.extend(items)
        else:
            picked.extend(rng.sample(items, n))
    rng.shuffle(picked)
    return picked


def sample_mmlu_pro(outdir: Path) -> dict:
    """TIGER-Lab/MMLU-Pro — 100 stratified across 14 subjects."""
    ds = load_dataset("TIGER-Lab/MMLU-Pro", split="test")
    rows = []
    for i, ex in enumerate(ds):
        rows.append({
            "_idx": i,
            "question": ex["question"],
            "options": ex["options"],
            "answer": ex["answer"],
            "answer_index": ex["answer_index"],
            "category": ex["category"],
        })
    rng = random.Random(SEED)
    picked = _stratified_pick(rows, lambda r: r["category"], 100, rng)

    csv_path = outdir / "datasets" / "sampled_mmlu_pro.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["question_id", "subject_or_category", "question",
                    "options_json", "expected"])
        for p in picked:
            qid = f"mmlu_pro_{p['_idx']:05d}_{_short_hash(p['question'])}"
            w.writerow([qid, p["category"], p["question"],
                        json.dumps(p["options"], ensure_ascii=False),
                        p["answer"]])
    dist: dict[str, int] = defaultdict(int)
    for p in picked:
        dist[p["category"]] += 1
    return {"path": str(csv_path), "n": len(picked), "dist": dict(dist),
            "sample_example": picked[0]}


def sample_gpqa_diamond(outdir: Path) -> dict:
    """Idavidrein/gpqa — load gpqa_diamond.csv directly via hf_hub_download.

    The repo no longer ships a HuggingFace loading script, only raw CSVs.
    Full 198 questions, option order shuffled per-question (seed-based).
    """
    from huggingface_hub import hf_hub_download

    csv_local = hf_hub_download(
        repo_id="Idavidrein/gpqa",
        filename="gpqa_diamond.csv",
        repo_type="dataset",
    )

    rng = random.Random(SEED)
    rows = []
    with open(csv_local, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, ex in enumerate(reader):
            opts = [ex["Correct Answer"].strip(),
                    ex["Incorrect Answer 1"].strip(),
                    ex["Incorrect Answer 2"].strip(),
                    ex["Incorrect Answer 3"].strip()]
            per_q_rng = random.Random(SEED + i)
            indexed = list(enumerate(opts))
            per_q_rng.shuffle(indexed)
            ordered = [t[1] for t in indexed]
            correct_letter = "ABCD"[next(j for j, t in enumerate(indexed)
                                         if t[0] == 0)]
            rows.append({
                "_idx": i,
                "question": ex["Question"].strip(),
                "options": ordered,
                "answer_letter": correct_letter,
                "domain": (ex.get("High-level domain")
                           or ex.get("Subdomain") or "unknown").strip(),
            })
    rng.shuffle(rows)

    csv_path = outdir / "datasets" / "sampled_gpqa_diamond.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["question_id", "subject_or_category", "question",
                    "options_json", "expected"])
        for p in rows:
            qid = f"gpqa_{p['_idx']:04d}_{_short_hash(p['question'])}"
            w.writerow([qid, p["domain"], p["question"],
                        json.dumps(p["options"], ensure_ascii=False),
                        p["answer_letter"]])
    dist: dict[str, int] = defaultdict(int)
    for p in rows:
        dist[p["domain"]] += 1
    return {"path": str(csv_path), "n": len(rows), "dist": dict(dist),
            "sample_example": rows[0]}


def sample_truthfulqa_mc1(outdir: Path) -> dict:
    """truthfulqa/truthful_qa config multiple_choice — 100 stratified by category.

    The `multiple_choice` config has no `category` field; only `generation`
    does. Both configs share the same 817 questions identified by text,
    so we join via question text to recover category.
    """
    gen = load_dataset("truthfulqa/truthful_qa", "generation",
                       split="validation")
    cat_by_q = {ex["question"]: (ex.get("category") or "Misc") for ex in gen}

    ds = load_dataset("truthfulqa/truthful_qa", "multiple_choice",
                      split="validation")
    rows = []
    for i, ex in enumerate(ds):
        choices = ex["mc1_targets"]["choices"]
        labels = ex["mc1_targets"]["labels"]
        correct_index = labels.index(1)
        rows.append({
            "_idx": i,
            "question": ex["question"],
            "options": choices,
            "answer_index": correct_index + 1,
            "category": cat_by_q.get(ex["question"], "Misc"),
        })
    rng = random.Random(SEED)
    picked = _stratified_pick(rows, lambda r: r["category"], 100, rng)

    csv_path = outdir / "datasets" / "sampled_truthfulqa_mc1.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["question_id", "subject_or_category", "question",
                    "options_json", "expected"])
        for p in picked:
            qid = f"truthqa_{p['_idx']:04d}_{_short_hash(p['question'])}"
            w.writerow([qid, p["category"], p["question"],
                        json.dumps(p["options"], ensure_ascii=False),
                        str(p["answer_index"])])
    dist: dict[str, int] = defaultdict(int)
    for p in picked:
        dist[p["category"]] += 1
    return {"path": str(csv_path), "n": len(picked), "dist": dict(dist),
            "sample_example": picked[0]}


def sample_simpleqa(outdir: Path) -> dict:
    """basicv8vc/SimpleQA — 100 stratified by topic. Fallback to
    openai/simple-qa-verified if primary fails."""
    rows = []
    try:
        ds = load_dataset("basicv8vc/SimpleQA", split="test")
        source = "basicv8vc/SimpleQA"
        for i, ex in enumerate(ds):
            # Schema: problem, answer, metadata (str of Python dict repr,
            # not JSON — needs ast.literal_eval).
            meta = ex.get("metadata") or "{}"
            if isinstance(meta, str):
                try:
                    meta = ast.literal_eval(meta)
                except (ValueError, SyntaxError):
                    try:
                        meta = json.loads(meta)
                    except json.JSONDecodeError:
                        meta = {}
            topic = (meta.get("topic") if isinstance(meta, dict) else None) or "general"
            rows.append({
                "_idx": i,
                "question": ex.get("problem") or ex.get("question") or "",
                "answer": ex.get("answer") or "",
                "topic": topic,
            })
    except Exception as e1:
        print(f"  basicv8vc/SimpleQA failed: {e1}", file=sys.stderr)
        try:
            ds = load_dataset("openai/simple-qa-verified", split="test")
            source = "openai/simple-qa-verified"
            for i, ex in enumerate(ds):
                topic = ex.get("topic") or ex.get("category") or "general"
                rows.append({
                    "_idx": i,
                    "question": ex.get("problem") or ex.get("question") or "",
                    "answer": ex.get("answer") or "",
                    "topic": topic,
                })
        except Exception as e2:
            print(f"  openai/simple-qa-verified also failed: {e2}",
                  file=sys.stderr)
            raise RuntimeError(
                "Both SimpleQA sources unreachable; abort per spec §3.1"
            )

    rng = random.Random(SEED)
    picked = _stratified_pick(rows, lambda r: r["topic"], 100, rng)

    csv_path = outdir / "datasets" / "sampled_simpleqa.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["question_id", "subject_or_category", "question",
                    "options_json", "expected"])
        for p in picked:
            qid = f"simpleqa_{p['_idx']:04d}_{_short_hash(p['question'])}"
            w.writerow([qid, p["topic"], p["question"], "[]", p["answer"]])
    dist: dict[str, int] = defaultdict(int)
    for p in picked:
        dist[p["topic"]] += 1
    return {"path": str(csv_path), "n": len(picked), "dist": dict(dist),
            "sample_example": picked[0], "source": source}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    outdir = Path(args.outdir)
    (outdir / "datasets").mkdir(parents=True, exist_ok=True)

    summary = {}
    for name, fn in [
        ("mmlu_pro", sample_mmlu_pro),
        ("gpqa_diamond", sample_gpqa_diamond),
        ("truthfulqa_mc1", sample_truthfulqa_mc1),
        ("simpleqa", sample_simpleqa),
    ]:
        print(f"\n=== {name} ===", flush=True)
        try:
            info = fn(outdir)
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}", flush=True)
            summary[name] = {"error": str(e)}
            continue
        summary[name] = info
        print(f"  → {info['path']}  (n={info['n']})")
        print(f"  distribution ({len(info['dist'])} strata):")
        for k, v in sorted(info["dist"].items(), key=lambda kv: -kv[1])[:20]:
            print(f"    {k:<40} {v}")
        ex = info["sample_example"]
        print(f"  sample example:")
        print(f"    question[:120]: {str(ex.get('question',''))[:120]}")
        if "options" in ex:
            opts = ex["options"][:3]
            print(f"    options[:3]: {opts}")
        for k in ("answer", "answer_letter", "answer_index"):
            if k in ex:
                print(f"    {k}: {ex[k]}")

    with (outdir / "datasets" / "_sampling_summary.json").open("w") as fh:
        # Drop sample_example to keep summary compact.
        clean = {k: {kk: vv for kk, vv in v.items() if kk != "sample_example"}
                 for k, v in summary.items()}
        json.dump(clean, fh, indent=2, ensure_ascii=False)
    print(f"\nSummary → {outdir / 'datasets' / '_sampling_summary.json'}")


if __name__ == "__main__":
    main()
