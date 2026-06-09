from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ..state.session_state import SessionState
from ..kernel.routing_engine import RoutingEngine


def _build_engine(
    use_adapter: bool,
    docs_dir: str | None,
    web_search: bool = False,
    preset: str = "general",
) -> RoutingEngine:
    """Build a RoutingEngine with optional Ollama adapter, local RAG, and web search."""
    adapter            = None
    rag                = None
    web_search_adapter = None

    if use_adapter:
        try:
            from ..adapters.ollama_adapter import OllamaAdapter
            endpoint   = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
            endpoint_2 = os.environ.get("OLLAMA_ENDPOINT_2", None)
            model_name = os.environ.get("OLLAMA_MODEL",    "phi4-mini:latest")
            adapter    = OllamaAdapter(
                endpoint=endpoint, model_name=model_name,
                second_endpoint=endpoint_2, dual_pass=bool(endpoint_2),
            )
        except Exception as exc:
            print(f"[warn] Adapter unavailable: {exc}", file=sys.stderr)

    if docs_dir:
        try:
            from ..retrieval.embedder import SentenceTransformerEmbedder
            from ..retrieval.rag_pipeline import LocalRAGPipeline
            embedder = SentenceTransformerEmbedder()
            rag      = LocalRAGPipeline(embedder=embedder)
            rag.ingest_directory(docs_dir)
            print(f"[info] RAG indexed {len(rag._index.items)} chunks from {docs_dir}", file=sys.stderr)
        except Exception as exc:
            print(f"[warn] RAG unavailable: {exc}", file=sys.stderr)

    if web_search:
        try:
            from ..adapters.web_search_adapter import make_default_adapter
            web_search_adapter = make_default_adapter()
            print(f"[info] Web search adapter: {web_search_adapter.PROVIDER_NAME}", file=sys.stderr)
        except Exception as exc:
            print(f"[warn] Web search unavailable: {exc}", file=sys.stderr)

    # Kiwix local fallback (no API key required)
    kiwix_adapter = None
    try:
        from ..adapters.kiwix_search_adapter import KiwixSearchAdapter
        _kiwix = KiwixSearchAdapter()
        if _kiwix.is_available():
            kiwix_adapter = _kiwix
            print(f"[info] Kiwix: available (local Wikipedia)", file=sys.stderr)
    except Exception:
        pass

    return RoutingEngine(
        adapter=adapter,
        rag_pipeline=rag,
        web_search_adapter=web_search_adapter,
        kiwix_adapter=kiwix_adapter,
        verify_preset=preset,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Möbius Runtime CLI")
    parser.add_argument("--input",       required=True,  help="User input for this turn")
    parser.add_argument("--session",     default=None,   help="Path to session JSON file (load/save)")
    parser.add_argument("--adapter",     action="store_true", help="Enable Ollama adapter")
    parser.add_argument("--docs",        default=None,   help="Directory to index for local RAG")
    parser.add_argument("--export",      default=None,   help="Export session to this JSON path after turn")
    parser.add_argument("--trace",       action="store_true", help="Include trace in output")
    parser.add_argument("--web-search",  action="store_true", help="Enable web search for verify route")
    parser.add_argument("--preset",      default="general",   help="Verify preset: general|policy|legal|educational")
    args = parser.parse_args()

    # Load or create session
    state = SessionState()
    if args.session and Path(args.session).exists():
        state = SessionState.import_json(Path(args.session).read_text())

    # Build engine
    engine = _build_engine(use_adapter=args.adapter, docs_dir=args.docs, web_search=args.web_search, preset=args.preset)

    # Run one turn
    result = engine.evaluate(args.input, state)

    # Build output
    output: dict = {
        "route":           result.decision.route,
        "active_language": result.session_state.active_language,
        "response":        result.response_text,
    }
    if result.sources:
        output["sources"] = result.sources
    if result.decision.verify_outcome if hasattr(result.decision, "verify_outcome") else None:
        output["verify_outcome"] = getattr(result.decision, "verify_outcome", None)
    if args.trace:
        output["trace"] = result.trace

    print(json.dumps(output, ensure_ascii=False, indent=2))

    # Save session
    if args.session:
        Path(args.session).write_text(result.session_state.export_json())

    # Export session
    if args.export:
        Path(args.export).write_text(result.session_state.export_json())


if __name__ == "__main__":
    main()
