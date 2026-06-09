"""CLI: python -m benchmarks.operate_fr.harness.report_cli --summary X.json --out Y.md"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .report import render_report, write_report_to


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="OPERATE-FR Markdown reporter")
    p.add_argument("--summary", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--profile", default="unknown")
    p.add_argument("--suite", default="smoke100")
    p.add_argument("--section-label", default="neutral_baseline",
                   choices=["neutral_baseline", "mmv_side_technical"])
    p.add_argument("--extra-notes", default="")
    args = p.parse_args(argv)

    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    text = render_report(
        summary,
        profile_name=args.profile,
        suite_name=args.suite,
        section_label=args.section_label,
        extra_notes=args.extra_notes,
    )
    write_report_to(Path(args.out), text)
    print(f"Wrote report → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
