"""Secretary CLI — `python -m addons.secretary <verb> ...`.

This addon is the Claude-supervised, MMV-Large-only assistant layer.
It sits ABOVE the frozen MMV Core (per docs/MMV_CORE_FREEZE_POLICY.md
and docs/SECRETARY_ADDON_STRATEGY.md) and never modifies Core surfaces.

Verbs:

  version
      Print the current MMV-Large release binding (release name,
      profile, model, freeze note path). Run before any heavy job.

  bump --to <release> --profile <name> --freeze-note <path> --frozen-at <date>
       [--profile-path <yaml>] [--model <id>] [--endpoint <url>]
       [--backend <name>] [--harness-root <dir>] [--api-key-env <var>]
       [--short-name <name>]
      Overwrite operate-fr-bench/releases/large/current.yaml. After
      bump, every subsequent invocation uses the new release.

  review-packet --target <dir> [--out <path>]
                [--with-synthesis [--dry-run-synthesis]]
      Build a Markdown digest of the human-review packet (5 CSVs +
      summary.md). Writes to state/digests/ by default. Pure structural
      compression by default; `--with-synthesis` adds an MMV-Large
      narrative section (requires api_key_env to be set).

  handoff [--install] [--force] [--repo-root <dir>] [--out <path>]
      Build a cross-agent shared-memory readiness digest. With explicit
      --install, create AGENTS.md and docs/current/HANDOFF.md templates.
      With --next-agent-packet, write the minimal packet to hand to the
      next local AI agent.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from addons.secretary.explorers import (
    bench_summary as bench_summary_mod,
    docs_md as docs_md_mod,
    eval_results as eval_results_mod,
    git_history as git_history_mod,
    handoff as handoff_mod,
    pattern_library as pattern_library_mod,
    repo_grep as repo_grep_mod,
)
from addons.secretary.explorers.review_packet import (
    build_digest, build_synthesis_prompt,
)
from addons.secretary.release import (
    DEFAULT_POINTER,
    REPO_ROOT,
    ActiveRelease,
    bump_active_release,
    load_active_release,
)
from addons.secretary.state.audit import AuditLogger
from addons.secretary.state.halt import HaltRequested, halt_check

import yaml


DEFAULT_DIGEST_DIR = REPO_ROOT / "addons" / "secretary" / "state" / "digests"
PERMISSION_LADDER = REPO_ROOT / "addons" / "secretary" / "permission_ladder.yaml"


def _summary_line(active: ActiveRelease) -> str:
    return (
        f"{active.short_name} (frozen {active.frozen_at}, "
        f"profile={active.profile_name}, model={active.provider_model_id})"
    )


def _cmd_version(args: argparse.Namespace) -> int:
    pointer = Path(args.pointer) if args.pointer else DEFAULT_POINTER
    with AuditLogger("version", args={"pointer": str(pointer)}) as log:
        active = load_active_release(pointer)
        print(_summary_line(active))
        print(f"  release         : {active.release}")
        print(f"  profile_name    : {active.profile_name}")
        print(f"  profile_path    : {active.profile_path}")
        print(f"  harness_root    : {active.harness_root}")
        print(f"  freeze_note     : {active.freeze_note}")
        print(f"  provider_backend: {active.provider_backend}")
        print(f"  provider_endpt  : {active.provider_endpoint}")
        print(f"  provider_model  : {active.provider_model_id}")
        print(f"  api_key_env     : {active.api_key_env}")
        print(f"  frozen_at       : {active.frozen_at}")
        print(f"  pointer         : {pointer}")
        log.milestone("resolved", release=active.release)
    return 0


def _cmd_bump(args: argparse.Namespace) -> int:
    pointer = Path(args.pointer) if args.pointer else DEFAULT_POINTER
    with AuditLogger("bump", args={
        "pointer": str(pointer), "to": args.to,
        "profile": args.profile, "freeze_note": args.freeze_note,
    }) as log:
        active = bump_active_release(
            release=args.to,
            profile_name=args.profile,
            freeze_note=args.freeze_note,
            frozen_at=args.frozen_at or datetime.now(timezone.utc).date().isoformat(),
            pointer_path=pointer,
            short_name=args.short_name,
            profile_path=args.profile_path,
            harness_root=args.harness_root,
            provider_backend=args.backend,
            provider_endpoint=args.endpoint,
            provider_model_id=args.model,
            api_key_env=args.api_key_env,
        )
        print(f"bumped: {pointer}")
        print(f"active: {_summary_line(active)}")
        log.milestone("bumped", release=active.release, profile=active.profile_name)
    return 0


def _cmd_review_packet(args: argparse.Namespace) -> int:
    import os
    target = Path(args.target).resolve()
    with AuditLogger("review-packet", args={
        "target": str(target),
        "out": args.out,
        "with_synthesis": bool(args.with_synthesis),
        "dry_run_synthesis": bool(args.dry_run_synthesis),
    }) as log:
        release_line: str | None = None
        active: ActiveRelease | None = None
        try:
            active = load_active_release()
            release_line = _summary_line(active)
        except Exception as e:
            print(f"warning: release pointer not available ({e})", file=sys.stderr)
            log.milestone("pointer_unavailable", error=str(e))

        halt_check()
        digest = build_digest(target, release_line=release_line)
        log.milestone("structural_digest", chars=len(digest))

        if args.with_synthesis:
            prompt = build_synthesis_prompt(digest)
            if args.dry_run_synthesis:
                digest += (
                    "\n## Synthesis prompt (dry-run, not sent)\n\n"
                    "```\n" + prompt + "\n```\n"
                )
                log.milestone("synthesis_dry_run", prompt_chars=len(prompt))
            elif active is None or not os.environ.get(active.api_key_env, "").strip():
                digest += (
                    f"\n## Synthesis skipped\n\n"
                    f"`{active.api_key_env}` is not set in the environment, so "
                    f"MMV-Large was not called. Re-run with the key exported, or "
                    f"pass `--dry-run-synthesis` to see the prompt that would "
                    f"have been sent.\n"
                )
                log.milestone("synthesis_skipped", reason="api_key_env_unset")
            else:
                from addons.secretary.providers.large import call_large
                halt_check()
                print("synthesizing via MMV Large ...", file=sys.stderr)
                log.milestone("synthesis_call_started")
                resp = call_large(prompt)
                digest += (
                    f"\n## MMV-Large synthesis ({resp.release})\n\n"
                )
                if resp.error:
                    digest += (
                        f"_synthesis failed_: `{resp.error}`\n"
                    )
                    log.milestone(
                        "synthesis_failed", error=resp.error,
                        latency_ms=resp.latency_ms,
                    )
                else:
                    digest += resp.text.strip() + "\n"
                    digest += (
                        f"\n---\n"
                        f"_model_: `{resp.model_id}` · _latency_: {resp.latency_ms}ms"
                        f" · _tokens_: in={resp.tokens_in} out={resp.tokens_out}\n"
                    )
                    log.milestone(
                        "synthesis_ok", model=resp.model_id,
                        latency_ms=resp.latency_ms,
                        tokens_in=resp.tokens_in, tokens_out=resp.tokens_out,
                    )

        if args.out:
            out_path = Path(args.out)
        else:
            DEFAULT_DIGEST_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            out_path = DEFAULT_DIGEST_DIR / f"review_packet_{stamp}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(digest, encoding="utf-8")
        print(f"digest: {out_path}")
        print(f"  size: {len(digest)} chars, {digest.count(chr(10)) + 1} lines")
        log.milestone("digest_written", out=str(out_path), chars=len(digest))
    return 0


def _write_digest(text: str, out: str | None, verb: str) -> Path:
    """Common output handling: write digest to --out or state/digests/."""
    if out:
        path = Path(out)
    else:
        DEFAULT_DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = DEFAULT_DIGEST_DIR / f"{verb}_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _maybe_release_line() -> str | None:
    try:
        return _summary_line(load_active_release())
    except Exception:
        return None


def _cmd_eval_results(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    with AuditLogger("eval-results", args={
        "target": str(target), "out": args.out,
    }) as log:
        halt_check()
        digest = eval_results_mod.build_digest(
            target, release_line=_maybe_release_line(),
        )
        log.milestone("digested", chars=len(digest))
        out_path = _write_digest(digest, args.out, "eval_results")
        print(f"digest: {out_path}")
        print(f"  size: {len(digest)} chars, {digest.count(chr(10)) + 1} lines")
        log.milestone("written", out=str(out_path))
    return 0


def _cmd_git_history(args: argparse.Namespace) -> int:
    with AuditLogger("git-history", args={
        "since": args.since, "until": args.until,
        "last": args.last, "paths": args.paths, "out": args.out,
    }) as log:
        halt_check()
        digest = git_history_mod.build_digest(
            repo=REPO_ROOT,
            since=args.since, until=args.until,
            last=args.last, paths=args.paths or None,
            release_line=_maybe_release_line(),
        )
        log.milestone("digested", chars=len(digest))
        out_path = _write_digest(digest, args.out, "git_history")
        print(f"digest: {out_path}")
        print(f"  size: {len(digest)} chars, {digest.count(chr(10)) + 1} lines")
        log.milestone("written", out=str(out_path))
    return 0


def _cmd_bench_summary(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    with AuditLogger("bench-summary", args={
        "target": str(target), "out": args.out,
    }) as log:
        halt_check()
        digest = bench_summary_mod.build_digest(
            target, release_line=_maybe_release_line(),
        )
        log.milestone("digested", chars=len(digest))
        out_path = _write_digest(digest, args.out, "bench_summary")
        print(f"digest: {out_path}")
        print(f"  size: {len(digest)} chars, {digest.count(chr(10)) + 1} lines")
        log.milestone("written", out=str(out_path))
    return 0


def _cmd_repo_grep(args: argparse.Namespace) -> int:
    with AuditLogger("repo-grep", args={
        "pattern": args.pattern, "paths": args.paths,
        "ignore_case": bool(args.ignore_case), "out": args.out,
    }) as log:
        halt_check()
        digest = repo_grep_mod.build_digest(
            args.pattern,
            paths=args.paths or None,
            repo=REPO_ROOT,
            ignore_case=bool(args.ignore_case),
            release_line=_maybe_release_line(),
        )
        log.milestone("digested", chars=len(digest))
        out_path = _write_digest(digest, args.out, "repo_grep")
        print(f"digest: {out_path}")
        print(f"  size: {len(digest)} chars, {digest.count(chr(10)) + 1} lines")
        log.milestone("written", out=str(out_path))
    return 0


def _cmd_pattern_library(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve() if args.target else (
        REPO_ROOT / "config" / "pattern_library"
    )
    with AuditLogger("pattern-library", args={
        "target": str(target), "out": args.out,
    }) as log:
        halt_check()
        digest = pattern_library_mod.build_digest(
            target, release_line=_maybe_release_line(),
        )
        log.milestone("digested", chars=len(digest))
        out_path = _write_digest(digest, args.out, "pattern_library")
        print(f"digest: {out_path}")
        print(f"  size: {len(digest)} chars, {digest.count(chr(10)) + 1} lines")
        log.milestone("written", out=str(out_path))
    return 0


def _cmd_docs(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve() if args.target else (
        REPO_ROOT / "docs"
    )
    with AuditLogger("docs", args={
        "target": str(target),
        "recent_days": args.recent_days,
        "out": args.out,
    }) as log:
        halt_check()
        digest = docs_md_mod.build_digest(
            target,
            recent_days=args.recent_days,
            release_line=_maybe_release_line(),
        )
        log.milestone("digested", chars=len(digest))
        out_path = _write_digest(digest, args.out, "docs")
        print(f"digest: {out_path}")
        print(f"  size: {len(digest)} chars, {digest.count(chr(10)) + 1} lines")
        log.milestone("written", out=str(out_path))
    return 0


def _cmd_handoff(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).resolve() if args.repo_root else REPO_ROOT
    with AuditLogger("handoff", args={
        "repo_root": str(root),
        "install": bool(args.install),
        "force": bool(args.force),
        "next_agent_packet": bool(args.next_agent_packet),
        "include_file": args.include_file,
        "out": args.out,
    }) as log:
        halt_check()
        if args.install:
            results = handoff_mod.install_common_files(
                root,
                force=bool(args.force),
            )
            for result in results:
                print(f"{result.action}: {result.path}")
            log.milestone(
                "installed",
                results=[
                    {"path": str(r.path), "action": r.action}
                    for r in results
                ],
            )
        if args.next_agent_packet:
            digest = handoff_mod.build_next_agent_packet(
                root,
                task_files=args.include_file or None,
                release_line=_maybe_release_line(),
            )
            out_prefix = "next_ai_packet"
        else:
            digest = handoff_mod.build_digest(
                root,
                release_line=_maybe_release_line(),
            )
            out_prefix = "handoff"
        log.milestone("digested", chars=len(digest))
        out_path = _write_digest(digest, args.out, out_prefix)
        print(f"digest: {out_path}")
        print(f"  size: {len(digest)} chars, {digest.count(chr(10)) + 1} lines")
        log.milestone("written", out=str(out_path))
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    """Drill into one verb: its permission spec + recent invocations."""
    import json

    with AuditLogger("explain", args={"verb": args.verb}) as log:
        if not PERMISSION_LADDER.exists():
            print(f"permission ladder missing: {PERMISSION_LADDER}",
                  file=sys.stderr)
            log.milestone("ladder_missing")
            return 2
        data = yaml.safe_load(
            PERMISSION_LADDER.read_text(encoding="utf-8")
        ) or {}
        verbs = data.get("verbs") or {}
        spec = verbs.get(args.verb)
        if spec is None:
            print(f"verb {args.verb!r} not declared in permission_ladder.yaml.")
            print(f"declared verbs: {sorted(verbs)}", file=sys.stderr)
            log.milestone("verb_not_found", verb=args.verb)
            return 2

        print(f"# {args.verb}")
        print()
        desc = (spec.get("description") or "").strip()
        if desc:
            print(desc)
            print()
        for key in ("reads", "writes", "network", "side_effects", "halt_aware"):
            val = spec.get(key)
            if val is None or val == [] or val == "":
                print(f"  {key:14s}: (none)")
            elif isinstance(val, (list, dict)):
                print(f"  {key:14s}:")
                for line in yaml.safe_dump(val, allow_unicode=True).splitlines():
                    print(f"    {line}")
            else:
                print(f"  {key:14s}: {val}")

        # Recent invocations from state/logs/
        from addons.secretary.state.audit import LOGS_DIR
        if LOGS_DIR.exists():
            logs = sorted(
                LOGS_DIR.glob(f"{args.verb}_*.jsonl"),
                key=lambda p: p.stat().st_mtime, reverse=True,
            )[:args.history]
            if logs:
                print()
                print(f"## Recent invocations (last {len(logs)})")
                for path in logs:
                    records = [
                        json.loads(line) for line in
                        path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    if not records:
                        continue
                    start = records[0]
                    end = records[-1] if records[-1].get("event") == "end" else None
                    status = (end or {}).get("status", "?")
                    duration = (end or {}).get("duration_ms", "?")
                    print(
                        f"  - {start.get('ts','?')} status={status} "
                        f"duration={duration}ms file={path.name}"
                    )
                    milestones = [r.get("note") for r in records if r.get("event") == "milestone"]
                    if milestones:
                        print(f"    milestones: {', '.join(filter(None, milestones))}")
        log.milestone("explained", verb=args.verb)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    """Print the permission ladder — what each verb reads / writes / calls."""
    with AuditLogger("list", args={}) as log:
        if not PERMISSION_LADDER.exists():
            print(f"permission ladder missing: {PERMISSION_LADDER}",
                  file=sys.stderr)
            log.milestone("ladder_missing")
            return 2
        data = yaml.safe_load(
            PERMISSION_LADDER.read_text(encoding="utf-8")
        ) or {}
        verbs = data.get("verbs") or {}
        print(f"Permission ladder ({PERMISSION_LADDER.name})")
        print(f"  schema_version: {data.get('schema_version', '?')}")
        print()
        for name in sorted(verbs):
            spec = verbs[name] or {}
            desc = (spec.get("description") or "").strip().splitlines()
            print(f"  {name}:")
            for line in desc[:2]:
                print(f"    {line}")
            reads = spec.get("reads") or []
            writes = spec.get("writes") or []
            network = spec.get("network")
            halt_aware = spec.get("halt_aware", False)
            print(f"    reads     : {reads if reads else '(none)'}")
            print(f"    writes    : {writes if writes else '(none)'}")
            print(f"    network   : "
                  f"{'yes (see permission_ladder.yaml)' if network else 'no'}")
            print(f"    halt_aware: {halt_aware}")
            print()
        log.milestone("listed", n_verbs=len(verbs))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m addons.secretary",
        description="Claude-supervised assistant for token-heavy MMV work.",
    )
    p.add_argument(
        "--pointer", default=None,
        help="Path to the release pointer YAML (default: operate-fr-bench/releases/large/current.yaml)",
    )
    sub = p.add_subparsers(dest="verb", required=True)

    sp_version = sub.add_parser("version", help="Print current MMV-Large binding.")
    sp_version.set_defaults(func=_cmd_version)

    sp_bump = sub.add_parser("bump", help="Update the release pointer to a new RC.")
    sp_bump.add_argument("--to", required=True, help="Release name, e.g. MMV-L-RC3.4")
    sp_bump.add_argument("--short-name", default=None)
    sp_bump.add_argument(
        "--profile", required=True,
        help="Profile name inside the config YAML (e.g. 120b_route_transformer_plus_validator_v3_2)",
    )
    sp_bump.add_argument(
        "--freeze-note", required=True,
        help="Path to the FREEZE_NOTE markdown for this RC (relative to repo root or absolute)",
    )
    sp_bump.add_argument("--profile-path", default=None)
    sp_bump.add_argument("--harness-root", default=None)
    sp_bump.add_argument("--backend", default=None)
    sp_bump.add_argument("--endpoint", default=None)
    sp_bump.add_argument("--model", default=None)
    sp_bump.add_argument("--api-key-env", default=None)
    sp_bump.add_argument("--frozen-at", default=None, help="ISO date (default: today UTC)")
    sp_bump.set_defaults(func=_cmd_bump)

    sp_rp = sub.add_parser(
        "review-packet",
        help="Digest a human-review packet directory.",
    )
    sp_rp.add_argument(
        "--target", required=True,
        help="Path to the human_review_packet_* directory",
    )
    sp_rp.add_argument(
        "--out", default=None,
        help="Output digest path (default: addons/secretary/state/digests/review_packet_<ts>.md)",
    )
    sp_rp.add_argument(
        "--with-synthesis", action="store_true",
        help="Append MMV-Large synthesis (Top 3 priorities / Risks / Ignore). Requires the api_key_env named in the active-release pointer.",
    )
    sp_rp.add_argument(
        "--dry-run-synthesis", action="store_true",
        help="With --with-synthesis: build the prompt but do not call MMV Large. Embeds the prompt in the digest.",
    )
    sp_rp.set_defaults(func=_cmd_review_packet)

    sp_list = sub.add_parser(
        "list",
        help="Print the per-verb permission ladder.",
    )
    sp_list.set_defaults(func=_cmd_list)

    sp_ex = sub.add_parser(
        "explain",
        help="Drill into one verb: spec + recent invocations.",
    )
    sp_ex.add_argument("verb", help="Verb to explain (e.g. review-packet)")
    sp_ex.add_argument(
        "--history", type=int, default=3,
        help="Show last N invocations from state/logs/ (default: 3)",
    )
    sp_ex.set_defaults(func=_cmd_explain)

    sp_ev = sub.add_parser(
        "eval-results",
        help="Digest a generic eval directory (CSV/JSONL/log/md).",
    )
    sp_ev.add_argument("--target", required=True)
    sp_ev.add_argument("--out", default=None)
    sp_ev.set_defaults(func=_cmd_eval_results)

    sp_gh = sub.add_parser(
        "git-history",
        help="Digest recent git history (commits + diffs).",
    )
    sp_gh.add_argument("--since", default=None, help="git --since=<date>")
    sp_gh.add_argument("--until", default=None, help="git --until=<date>")
    sp_gh.add_argument("--last", type=int, default=20, help="N most recent commits")
    sp_gh.add_argument(
        "--paths", nargs="*", default=None,
        help="Limit to these path patterns",
    )
    sp_gh.add_argument("--out", default=None)
    sp_gh.set_defaults(func=_cmd_git_history)

    sp_bs = sub.add_parser(
        "bench-summary",
        help="Catalog files in a benchmarks/reports/ directory.",
    )
    sp_bs.add_argument("--target", required=True)
    sp_bs.add_argument("--out", default=None)
    sp_bs.set_defaults(func=_cmd_bench_summary)

    sp_rg = sub.add_parser(
        "repo-grep",
        help="Structured grep summary (top files / dirs / samples).",
    )
    sp_rg.add_argument("--pattern", required=True)
    sp_rg.add_argument(
        "--paths", nargs="*", default=None,
        help="Limit grep to these path patterns",
    )
    sp_rg.add_argument("--ignore-case", action="store_true")
    sp_rg.add_argument("--out", default=None)
    sp_rg.set_defaults(func=_cmd_repo_grep)

    sp_pl = sub.add_parser(
        "pattern-library",
        help="Digest config/pattern_library/ — counts, status, saturation.",
    )
    sp_pl.add_argument(
        "--target", default=None,
        help="Override library dir (default: config/pattern_library/)",
    )
    sp_pl.add_argument("--out", default=None, help="Override digest output path")
    sp_pl.set_defaults(func=_cmd_pattern_library)

    sp_docs = sub.add_parser(
        "docs",
        help="Catalog docs/*.md by topic prefix with titles and summaries.",
    )
    sp_docs.add_argument(
        "--target", default=None,
        help="Override docs dir (default: docs/)",
    )
    sp_docs.add_argument(
        "--recent-days", type=int, default=None,
        help="Limit to files modified within the last N days.",
    )
    sp_docs.add_argument("--out", default=None, help="Override digest output path")
    sp_docs.set_defaults(func=_cmd_docs)

    sp_handoff = sub.add_parser(
        "handoff",
        help="Digest or install cross-agent handoff files.",
    )
    sp_handoff.add_argument(
        "--repo-root",
        default=None,
        help="Target repo root (default: current MOBIUS_MMV repo).",
    )
    sp_handoff.add_argument(
        "--install",
        action="store_true",
        help="Create AGENTS.md and docs/current/HANDOFF.md if missing.",
    )
    sp_handoff.add_argument(
        "--force",
        action="store_true",
        help="With --install, overwrite existing shared-memory files.",
    )
    sp_handoff.add_argument(
        "--next-agent-packet",
        action="store_true",
        help="Write the minimal packet to hand to the next AI agent.",
    )
    sp_handoff.add_argument(
        "--include-file",
        action="append",
        default=None,
        help="Task-specific file to include in the next-agent read order.",
    )
    sp_handoff.add_argument("--out", default=None, help="Override digest output path")
    sp_handoff.set_defaults(func=_cmd_handoff)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except HaltRequested as e:
        print(f"halted: {e}", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
