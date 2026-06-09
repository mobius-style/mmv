# Clean RC3.2 backup (frozen)

This is the immutable snapshot of the **clean RC3.2** configuration that was
in effect before the 120B route-transformer experiment was introduced.

Do not edit these files; they are reference copies for reproducibility.

## Contents

- `mmv_rc32_120b.jsonl` — per-task run artifact (100 rows).
- `mmv_rc32_120b_summary.json` — component vector summary.
- `mmv_rc32_120b_report.md` — rendered Markdown report.
- `arm_b_doctrine.txt` — the Box A doctrine prefix used.
- `model_profiles.example.yaml.snapshot` — full profiles YAML at snapshot time.

## How to reproduce the clean run

```bash
cd operate-fr-bench
python -m harness.run_eval --suite configs/suite_smoke.yaml \
    --profile mmv_rc32_120b_clean \
    --out reports/<fresh>.jsonl
```

The `mmv_rc32_120b_clean` profile (added in configs/model_profiles.example.yaml)
preserves the original RC3.2 behaviour (Box A doctrine prefix only).
