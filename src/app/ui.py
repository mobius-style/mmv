"""Möbius Reflective Conversation Runtime — Chat UI (Phase 3)

Compatible with Gradio 6.x.

Launch:
    python -m src.app.ui [--adapter] [--docs DOCS_DIR] [--port 7860]

Environment variables:
    OLLAMA_ENDPOINT  default: http://localhost:11434
    OLLAMA_MODEL     default: phi4-mini:latest
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from typing import List

# ── Route badge colours ───────────────────────────────────────────────────────
ROUTE_COLOURS = {
    "answer":  ("#1a7f4b", "#e6f4ed"),
    "ask":     ("#1a5fa8", "#e6f0fb"),
    "verify":  ("#a87a1a", "#fbf3e6"),
    "abstain": ("#a81a1a", "#fbe6e6"),
}

ROUTE_LABELS = {
    "answer":  "✓ answer",
    "ask":     "? ask",
    "verify":  "⊛ verify",
    "abstain": "✕ abstain",
}


def _badge_html(route: str) -> str:
    fg, bg = ROUTE_COLOURS.get(route, ("#555", "#eee"))
    label  = ROUTE_LABELS.get(route, route)
    return (
        f'<span style="'
        f'background:{bg};color:{fg};border:1px solid {fg};'
        f'border-radius:4px;padding:1px 7px;font-size:0.78em;'
        f'font-weight:600;font-family:monospace;margin-right:6px;">'
        f'{label}</span>'
    )


def _why_html(trace: dict) -> str:
    reasons = trace.get("Reason", "")
    outcome = trace.get("VerifyOutcome")
    sources = trace.get("Sources", [])
    lines   = [f"<b>Reason:</b> {reasons}"]
    if outcome:
        outcome_colour = {
            "verify_success": "#1a7f4b",
            "verify_partial": "#a87a1a",
            "verify_failed":  "#a81a1a",
        }.get(outcome, "#555")
        lines.append(
            f'<b>Verify outcome:</b> <span style="color:{outcome_colour};font-weight:600;">{outcome}</span>'
        )
    # EAL fields
    admissibility = trace.get("Admissibility")
    if admissibility:
        lines.append(f"<b>Admissibility:</b> {admissibility}")
    why_web = trace.get("WhyWebSearchWasTriggered")
    if why_web:
        lines.append(f"<b>Why web search:</b> {why_web}")
    why_local = trace.get("WhyLocalEvidenceWasInsufficient")
    if why_local:
        lines.append(f"<b>Why not local:</b> {why_local}")
    freshness = trace.get("FreshnessState")
    conflict  = trace.get("ConflictState")
    if freshness or conflict:
        lines.append(f"<b>Freshness:</b> {freshness or '—'} &nbsp; <b>Conflict:</b> {conflict or '—'}")
    provider = trace.get("SearchProvider")
    if provider:
        lines.append(f"<b>Provider:</b> {provider}")
    # Sources
    if sources:
        if isinstance(sources[0], dict):
            src_items = "".join(
                f'<li><a href="{s.get('url','#')}" target="_blank">{s.get('source_name','?')}</a> — {s.get('title','')[:60]}</li>'
                for s in sources[:5]
            )
            lines.append(f"<b>Sources:</b><ul style='margin:2px 0 0 16px;'>{src_items}</ul>")
        else:
            lines.append(f"<b>Sources:</b> {', '.join(str(s) for s in sources[:5])}")
    return "<br>".join(lines)


def _state_md(state) -> str:
    lines = [
        f"**Session:** `{state.session_id[:8]}…`",
        f"**Language:** `{state.active_language}`",
        f"**Turn:** {state.current_turn}",
    ]
    if state.facts:
        lines.append("\n**Facts:**")
        lines += [f"- {f}" for f in state.facts[-3:]]
    if state.open_questions:
        lines.append("\n**Open questions:**")
        lines += [f"- {q}" for q in state.open_questions[-3:]]
    if state.corrections:
        lines.append(f"\n**Corrections:** {len(state.corrections)}")
    return "\n".join(lines)


# ── Engine factory ────────────────────────────────────────────────────────────

def _build_engine(
    use_adapter: bool,
    docs_dir: str | None,
    web_search: bool = False,
    preset: str = "general",
):
    from ..kernel.routing_engine import RoutingEngine
    adapter            = None
    rag                = None
    web_search_adapter = None

    if use_adapter:
        try:
            from ..adapters.ollama_adapter import OllamaAdapter
            endpoint   = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
            model_name = os.environ.get("OLLAMA_MODEL",    "phi4-mini:latest")
            adapter    = OllamaAdapter(endpoint=endpoint, model_name=model_name)
            print(f"[info] Adapter: {model_name} @ {endpoint}", file=sys.stderr)
        except Exception as exc:
            print(f"[warn] Adapter unavailable: {exc}", file=sys.stderr)

    if docs_dir:
        try:
            from ..retrieval.embedder import SentenceTransformerEmbedder
            from ..retrieval.rag_pipeline import LocalRAGPipeline
            embedder = SentenceTransformerEmbedder()
            rag      = LocalRAGPipeline(embedder=embedder)
            rag.ingest_directory(docs_dir)
            n = len(rag._index.items)
            print(f"[info] RAG: {n} chunks indexed from {docs_dir}", file=sys.stderr)
        except Exception as exc:
            print(f"[warn] RAG unavailable: {exc}", file=sys.stderr)

    if web_search:
        try:
            from ..adapters.web_search_adapter import make_default_adapter
            web_search_adapter = make_default_adapter()
            print(f"[info] Web search: {web_search_adapter.PROVIDER_NAME}", file=sys.stderr)
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


# ── Gradio app ────────────────────────────────────────────────────────────────

def build_app(use_adapter: bool = False, docs_dir: str | None = None, web_search: bool = False, preset: str = "general"):
    try:
        import gradio as gr
    except ImportError:
        print("Gradio not installed. Run: pip install gradio", file=sys.stderr)
        sys.exit(1)

    from ..state.session_state import SessionState

    engine = _build_engine(use_adapter=use_adapter, docs_dir=docs_dir, web_search=web_search, preset=preset)

    def _empty_session():
        return SessionState()

    # ── Chat handler ──────────────────────────────────────────────────────────

    def chat(user_message: str, history: List[dict], session_state_obj):
        if not user_message.strip():
            return history, session_state_obj, _state_md(session_state_obj), ""

        result = engine.evaluate(user_message, session_state_obj)
        route  = result.decision.route
        text   = result.response_text or ""
        trace  = result.trace

        badge      = _badge_html(route)
        why_detail = _why_html(trace)
        formatted  = (
            f"{badge}<br>{text}<br>"
            f'<details style="margin-top:6px;font-size:0.82em;color:#555;">'
            f'<summary>Why this route?</summary>'
            f'<div style="padding:4px 8px;">{why_detail}</div>'
            f'</details>'
        )

        history = history + [
            {"role": "user",      "content": user_message},
            {"role": "assistant", "content": formatted},
        ]
        return history, result.session_state, _state_md(result.session_state), ""

    # ── Correction handler ────────────────────────────────────────────────────

    def apply_correction(field: str, value: str, session_state_obj):
        if not value.strip():
            return session_state_obj, _state_md(session_state_obj), "No value provided."
        try:
            session_state_obj.apply_correction(field, value.strip())
            return session_state_obj, _state_md(session_state_obj), f"✓ Added to {field}."
        except ValueError as e:
            return session_state_obj, _state_md(session_state_obj), f"Error: {e}"

    # ── Export handler ────────────────────────────────────────────────────────

    def export_session(session_state_obj):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        tmp.write(session_state_obj.export_json())
        tmp.flush()
        return tmp.name

    # ── Reset handler ─────────────────────────────────────────────────────────

    def reset_session():
        new_state = SessionState()
        return [], new_state, _state_md(new_state), ""

    # ── UI layout (Gradio 6.x compatible) ────────────────────────────────────

    HEADER_HTML = """
    <div style="font-family:monospace;font-size:0.82em;color:#666;margin-bottom:4px;">
        Möbius Reflective Conversation Runtime &nbsp;·&nbsp; MMV
    </div>
    <h2 style="margin:0 0 4px 0;">
        A reflective runtime that decides how to help before it answers.
    </h2>
    <div style="font-size:0.8em;margin-bottom:12px;">
        <span style="color:#1a7f4b;font-weight:600;margin-right:10px;">✓ answer</span>
        <span style="color:#1a5fa8;font-weight:600;margin-right:10px;">? ask</span>
        <span style="color:#a87a1a;font-weight:600;margin-right:10px;">⊛ verify</span>
        <span style="color:#a81a1a;font-weight:600;">✕ abstain</span>
    </div>
    """

    with gr.Blocks() as demo:

        gr.HTML(HEADER_HTML)

        session_obj = gr.State(_empty_session)

        with gr.Row():

            # ── Left: Chat ────────────────────────────────────────────────────
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="Conversation",
                    height=520,
                )
                with gr.Row():
                    user_input = gr.Textbox(
                        placeholder="Type your question here…",
                        show_label=False,
                        scale=5,
                        lines=1,
                    )
                    send_btn = gr.Button("Send", variant="primary", scale=1)

                reset_btn = gr.Button("↺  New session", size="sm", variant="secondary")

            # ── Right: Session panel ──────────────────────────────────────────
            with gr.Column(scale=1, min_width=260):
                gr.Markdown("### Session State")
                state_display = gr.Markdown(value=_state_md(_empty_session()))

                gr.Markdown("---")
                gr.Markdown("**Add correction**")
                correction_field = gr.Dropdown(
                    choices=["facts", "assumptions", "open_questions", "constraints", "summary"],
                    value="facts",
                    label="Field",
                )
                correction_value  = gr.Textbox(label="Value", lines=1)
                correction_btn    = gr.Button("Apply", size="sm")
                correction_status = gr.Textbox(label="", interactive=False, lines=1)

                gr.Markdown("---")
                gr.Markdown("**Export session**")
                export_btn  = gr.Button("Download session JSON", size="sm")
                export_file = gr.File(label="Session file", interactive=False)

        # ── Event bindings ────────────────────────────────────────────────────

        send_inputs  = [user_input, chatbot, session_obj]
        send_outputs = [chatbot, session_obj, state_display, user_input]

        send_btn.click(chat,  inputs=send_inputs, outputs=send_outputs)
        user_input.submit(chat, inputs=send_inputs, outputs=send_outputs)

        reset_btn.click(
            reset_session,
            outputs=[chatbot, session_obj, state_display, user_input],
        )
        correction_btn.click(
            apply_correction,
            inputs=[correction_field, correction_value, session_obj],
            outputs=[session_obj, state_display, correction_status],
        )
        export_btn.click(
            export_session,
            inputs=[session_obj],
            outputs=[export_file],
        )

    return demo


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Möbius Chat UI")
    parser.add_argument("--adapter", action="store_true", help="Enable Ollama adapter")
    parser.add_argument("--docs",    default=None,        help="Directory to index for RAG")
    parser.add_argument("--port",    type=int, default=7860, help="Port (default: 7860)")
    parser.add_argument("--share",      action="store_true", help="Create public Gradio link")
    parser.add_argument("--web-search", action="store_true", help="Enable web search for verify route")
    parser.add_argument("--preset",     default="general",   help="Verify preset: general|policy|legal|educational")
    args = parser.parse_args()

    demo = build_app(use_adapter=args.adapter, docs_dir=args.docs, web_search=args.web_search, preset=args.preset)
    demo.launch(
        server_port=args.port,
        share=args.share,
    )


if __name__ == "__main__":
    main()
