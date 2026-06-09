# Clean RC3.2 backup — 120B path

Snapshot of the "clean RC3.2" 120B governed configuration before the
120B route-transformer work. Per spec, retained for ablation and
auditability.

## What this captured

- `arm_b_doctrine.txt.backup` — the Box A doctrine prefix used by the
  `mmv_rc32_120b` profile (verbatim from
  `eval/rc3_2/prefixes/arm_b_doctrine.txt` at backup time).
- `mmv_rc32_120b.jsonl` — Smoke-100 result rows from the clean RC3.2 run.
- `mmv_rc32_120b_summary.json` — component-vector summary.
- `mmv_rc32_120b_report.md` — rendered component-vector report.

## Profile (snapshot)

```yaml
mmv_rc32_120b:
  backend: openai_compatible
  base_url: https://api.groq.com/openai/v1
  model_id: openai/gpt-oss-120b
  prefix_file: eval/rc3_2/prefixes/arm_b_doctrine.txt
  temperature: 0.0
  max_tokens: 1024
  timeout_s: 60
  retry: 2
  api_key_env: GROQ_API_KEY
```

## How to re-run the backed-up configuration

The profile and prefix file are still present in the working tree; the
profile remains under the same name. Re-running is:

```bash
cd operate-fr-bench
python -m harness.run_eval --suite configs/suite_smoke.yaml \
    --profile mmv_rc32_120b --out reports/mmv_rc32_120b.jsonl
```

This backup is intentionally read-only — do not edit these files. If the
profile in the working tree is later changed in a way that breaks
reproduction, the snapshot here is the source of truth.
