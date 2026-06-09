"""Phase 2 explorer tests:

  - eval-results       (addons.secretary.explorers.eval_results)
  - git-history        (addons.secretary.explorers.git_history)
  - bench-summary      (addons.secretary.explorers.bench_summary)
  - repo-grep          (addons.secretary.explorers.repo_grep)

Each test exercises the explorer's build_digest() against a real
on-disk fixture (a directory or a git repo) and asserts that the
digest contains the structural facts a reader would expect. The tests
SKIP when the underlying fixture is absent so the suite stays green
in stripped-down checkouts.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from addons.secretary.cli import main
from addons.secretary.explorers import (
    bench_summary as bench_summary_mod,
    eval_results as eval_results_mod,
    git_history as git_history_mod,
    handoff as handoff_mod,
    repo_grep as repo_grep_mod,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


# ── eval-results ────────────────────────────────────────────────────


P9_EVIDENCE = REPO_ROOT / "eval" / "p9_evidence_pack_v1"


@pytest.mark.skipif(
    not P9_EVIDENCE.exists(),
    reason="eval/p9_evidence_pack_v1 not present",
)
def test_eval_results_digest_lists_files_and_counts_rows() -> None:
    md = eval_results_mod.build_digest(P9_EVIDENCE)
    assert "# Eval-results digest" in md
    assert "files_digested:" in md
    # Should mention at least one of the known jsonls.
    assert ".jsonl" in md
    # Row counts surface as `- rows: <n>` for tabular kinds.
    assert "- rows:" in md


@pytest.mark.skipif(
    not P9_EVIDENCE.exists(),
    reason="eval/p9_evidence_pack_v1 not present",
)
def test_eval_results_handles_unknown_target(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        eval_results_mod.build_digest(tmp_path / "does-not-exist")


# ── git-history ─────────────────────────────────────────────────────


def _is_git_repo() -> bool:
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(REPO_ROOT), check=True, capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


@pytest.mark.skipif(not _is_git_repo(), reason="not a git repo")
def test_git_history_digest_includes_recent_commits() -> None:
    md = git_history_mod.build_digest(repo=REPO_ROOT, last=3)
    assert "# Git-history digest" in md
    assert "commits: " in md
    # `## Commits (newest first)` only appears when there are commits.
    assert "Commits (newest first)" in md


@pytest.mark.skipif(not _is_git_repo(), reason="not a git repo")
def test_git_history_aggregates_distributions() -> None:
    shas = git_history_mod.list_commits(
        repo=REPO_ROOT, since=None, until=None, last=5, paths=None,
    )
    commits = [git_history_mod.describe(s, repo=REPO_ROOT) for s in shas]
    digest = git_history_mod.aggregate(commits)
    # Aggregate sanity: author counter sum equals commit count.
    assert sum(digest.authors.values()) == len(commits)


# ── bench-summary ───────────────────────────────────────────────────


BENCH_REPORTS = REPO_ROOT / "benchmarks" / "reports"


@pytest.mark.skipif(
    not BENCH_REPORTS.exists(),
    reason="benchmarks/reports not present",
)
def test_bench_summary_groups_by_family() -> None:
    md = bench_summary_mod.build_digest(BENCH_REPORTS)
    assert "# Bench-summary digest" in md
    # At least one family heading should appear.
    assert any(h in md for h in (
        "## comparison_md", "## summary_csv", "## summary_md",
        "## orchestrator", "## ablation",
    ))


# ── repo-grep ───────────────────────────────────────────────────────


def test_repo_grep_finds_known_pattern(tmp_path: Path) -> None:
    md = repo_grep_mod.build_digest(
        "RoutingEngine",
        paths=["src/kernel/routing_engine.py"],
        repo=REPO_ROOT,
    )
    assert "# Repo-grep digest" in md
    # The pattern occurs at least twice in routing_engine.py — sanity check.
    assert "total hits:" in md
    assert "routing_engine.py" in md


def test_repo_grep_handles_no_hits() -> None:
    md = repo_grep_mod.build_digest(
        "ZZZ_UNLIKELY_PATTERN_XYZ987",
        paths=["addons/secretary"],
        repo=REPO_ROOT,
    )
    assert "total hits: 0" in md


# ── CLI integration smoke ───────────────────────────────────────────


@pytest.mark.skipif(
    not P9_EVIDENCE.exists(),
    reason="eval/p9_evidence_pack_v1 not present",
)
def test_cli_eval_results_writes_digest(tmp_path: Path) -> None:
    out = tmp_path / "eval.md"
    rc = main([
        "eval-results", "--target", str(P9_EVIDENCE), "--out", str(out),
    ])
    assert rc == 0
    assert out.exists()
    assert "# Eval-results digest" in out.read_text(encoding="utf-8")


@pytest.mark.skipif(not _is_git_repo(), reason="not a git repo")
def test_cli_git_history_writes_digest(tmp_path: Path) -> None:
    out = tmp_path / "gh.md"
    rc = main(["git-history", "--last", "3", "--out", str(out)])
    assert rc == 0
    assert "# Git-history digest" in out.read_text(encoding="utf-8")


def test_cli_repo_grep_writes_digest(tmp_path: Path) -> None:
    out = tmp_path / "rg.md"
    rc = main([
        "repo-grep", "--pattern", "RoutingEngine",
        "--paths", "src/kernel",
        "--out", str(out),
    ])
    assert rc == 0
    assert "# Repo-grep digest" in out.read_text(encoding="utf-8")


# ── handoff ──────────────────────────────────────────────────────────


def test_handoff_digest_reports_shared_files(tmp_path: Path) -> None:
    (tmp_path / "addons/secretary/state/digests").mkdir(parents=True)
    (tmp_path / "addons/secretary/state/digests/sample.md").write_text(
        "# sample\n",
        encoding="utf-8",
    )
    md = handoff_mod.build_digest(tmp_path)
    assert "# Handoff digest" in md
    assert "`AGENTS.md`: missing" in md
    assert "sample.md" in md
    assert "## Give next AI" in md
    assert "docs/current/DOCS_AUTHORITY_MAP.md" in md


def test_handoff_install_creates_templates_without_overwrite(tmp_path: Path) -> None:
    results = handoff_mod.install_common_files(tmp_path)
    assert {r.action for r in results} == {"created"}
    agents = tmp_path / "AGENTS.md"
    handoff = tmp_path / "docs/current/HANDOFF.md"
    assert "Secretary Addon" in agents.read_text(encoding="utf-8")
    assert "Current Handoff" in handoff.read_text(encoding="utf-8")

    agents.write_text("keep me\n", encoding="utf-8")
    results = handoff_mod.install_common_files(tmp_path)
    assert any(r.path == agents and r.action == "skipped_existing" for r in results)
    assert agents.read_text(encoding="utf-8") == "keep me\n"


def test_cli_handoff_install_writes_digest(tmp_path: Path) -> None:
    out = tmp_path / "handoff.md"
    rc = main([
        "handoff",
        "--repo-root", str(tmp_path),
        "--install",
        "--out", str(out),
    ])
    assert rc == 0
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "docs/current/HANDOFF.md").exists()
    assert "# Handoff digest" in out.read_text(encoding="utf-8")


def test_next_agent_packet_lists_canon_and_read_order(tmp_path: Path) -> None:
    packet = handoff_mod.build_next_agent_packet(
        tmp_path,
        task_files=["docs/current/example.md"],
    )
    assert "# Next AI Handoff Packet" in packet
    assert "## What Is Canonical" in packet
    assert "docs/current/DOCS_AUTHORITY_MAP.md" in packet
    assert "docs/current/example.md" in packet
    assert "## What To Give The Next AI" in packet


def test_cli_handoff_next_agent_packet_writes_packet(tmp_path: Path) -> None:
    out = tmp_path / "packet.md"
    rc = main([
        "handoff",
        "--repo-root", str(tmp_path),
        "--next-agent-packet",
        "--include-file", "docs/current/example.md",
        "--out", str(out),
    ])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "# Next AI Handoff Packet" in text
    assert "docs/current/example.md" in text
