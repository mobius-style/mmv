#!/usr/bin/env python3
"""
src/ui/app.py — MOBIUS MMV v2 UI
Design: "Looks like a normal chat. Open Settings to find MOBIUS."

Usage:
    cd $HOME/デスクトップ/mobius_ai/MOBIUS_MMV
    mobius
    python src/ui/app.py
    → http://localhost:7860
"""
import sys, os, json, datetime
from zoneinfo import ZoneInfo
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv
_env_path = os.path.join(ROOT, ".env")
load_dotenv(_env_path, override=True)

import atexit
import pickle
import gradio as gr
from src.kernel.routing_engine import RoutingEngine, RoutingResult
from src.state.session_state import SessionState, UserProfileMemory, VerifiedFactsMemory
from src.adapters.inference_adapter import KernelRequest

# ── Timestamp helper ─────────────────────────────────────────────────────────
_TZ_CHOICES = [
    ("Auto (Browser)", "auto"),
    ("Asia/Tokyo (JST)", "Asia/Tokyo"),
    ("UTC", "UTC"),
    ("US/Eastern (EST)", "US/Eastern"),
    ("US/Pacific (PST)", "US/Pacific"),
    ("Europe/London (GMT/BST)", "Europe/London"),
]

def _format_ts(tz_name: str = "UTC") -> str:
    """Return formatted timestamp like [14:37 JST]."""
    try:
        zi = ZoneInfo(tz_name) if tz_name and tz_name != "auto" else ZoneInfo("UTC")
    except Exception:
        zi = ZoneInfo("UTC")
    now = datetime.datetime.now(tz=zi)
    abbr = now.strftime("%Z") or tz_name.split("/")[-1]
    return f"[{now.strftime('%H:%M')} {abbr}]"

# ── M-2 / M-3 persistence ───────────────────────────────────────────────────
M2_PATH = os.path.join(ROOT, "data/user_profile.json")
M3_PATH = os.path.join(ROOT, "data/verified_facts.pkl")

def _load_user_profile() -> UserProfileMemory:
    try:
        with open(M2_PATH) as f:
            d = json.load(f)
        return UserProfileMemory(**d)
    except Exception:
        return UserProfileMemory()

def _save_user_profile(profile: UserProfileMemory) -> None:
    try:
        os.makedirs(os.path.dirname(M2_PATH), exist_ok=True)
        with open(M2_PATH, "w") as f:
            json.dump({"preferred_language": profile.preferred_language,
                        "explanation_depth": profile.explanation_depth,
                        "last_updated": profile.last_updated}, f, ensure_ascii=False)
    except Exception:
        pass

def _load_verified_facts() -> VerifiedFactsMemory:
    try:
        with open(M3_PATH, "rb") as f:
            return pickle.load(f)
    except Exception:
        return VerifiedFactsMemory()

def _save_verified_facts(vf: VerifiedFactsMemory) -> None:
    try:
        os.makedirs(os.path.dirname(M3_PATH), exist_ok=True)
        with open(M3_PATH, "wb") as f:
            pickle.dump(vf, f)
    except Exception:
        pass

_m2_profile = _load_user_profile()
_m3_facts = _load_verified_facts()
print(f"[UI] M-2 UserProfile: loaded (lang={_m2_profile.preferred_language}, depth={_m2_profile.explanation_depth})")
print(f"[UI] M-3 VerifiedFacts: loaded ({len(_m3_facts.facts)} facts)")

# ── Engine initialization ────────────────────────────────────────────────────
try:
    from src.adapters.ollama_adapter import OllamaAdapter
    _ep1 = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
    _ep2 = os.environ.get("OLLAMA_ENDPOINT_2", None)
    _adapter = OllamaAdapter(
        endpoint=_ep1,
        model_name="qwen3.5:9b",
        second_endpoint=_ep2,
        dual_pass=bool(_ep2),
    )
    _mode = "dual-pass" if _ep2 else "single-pass"
    print(f"[UI] OllamaAdapter loaded: qwen3.5:9b ({_mode})")
except Exception as e:
    _adapter = None
    print(f"[UI] OllamaAdapter not available: {e} — routing-only mode")

_web_search = None
try:
    from src.adapters.brave_search_adapter import BraveSearchAdapter
    _brave = BraveSearchAdapter()
    if _brave.search("ping").provider == "brave" and bool(os.getenv("BRAVE_API_KEY", "")):
        _web_search = _brave
        print(f"[UI] Web search: {_brave.PROVIDER_NAME} (API key loaded)")
    else:
        print("[UI] Web search: BRAVE_API_KEY not configured — freshness queries limited")
except Exception as e:
    print(f"[UI] Web search unavailable: {e}")

_kiwix = None
try:
    from src.adapters.kiwix_search_adapter import KiwixSearchAdapter
    _k = KiwixSearchAdapter()
    if _k.is_available():
        _kiwix = _k
        print("[UI] Kiwix: available (local Wikipedia)")
except Exception:
    pass

_box_0 = None
try:
    from src.adapters.custom_rag_adapter import CustomRagAdapter as _CRA
    # Embedding Rule (docs/EMBEDDING_RULE.md, 2026-04-23): Box 0 uses
    # intfloat/multilingual-e5-large so self-reference queries in JA / EN / ZH
    # share one vector space. "query: " / "passage: " are the ME5 conventions.
    _b0 = _CRA(
        corpus_dir    = os.path.join(ROOT, "corpus_box_0"),
        data_dir      = os.path.join(ROOT, "data", "box_0"),
        watch         = False,
        model_name    = "intfloat/multilingual-e5-large",
        query_prefix  = "query: ",
        passage_prefix = "passage: ",
    )
    _b0.load()
    if _b0.is_available():
        _box_0 = _b0
        print(f"[UI] Box 0: {len(_b0._chunks)} chunks (canonical, ME5)")
except Exception:
    pass

_wiki = None
try:
    from src.adapters.wiki_adapter import WikiAdapter as _WA
    _wiki = _WA(
        index_path=os.path.join(ROOT, "Wiki/wiki_index_ivfpq_me5.faiss"),
        chunks_path=os.path.join(ROOT, "Wiki/wiki_chunks_clean.jsonl.gz"),
    )
    _wiki.load()
    _wiki_count = getattr(_wiki, 'chunk_count', lambda: 'unknown')()
    print(f"[UI] Wiki (Box W): available ({_wiki_count} vectors)")
except Exception as e:
    print(f"[UI] Wiki (Box W) unavailable: {e}")

# ── Box A Manager ──────────────────────────────────────────────────────────
_box_a_mgr = None
_DATA_DIR_A = os.path.join(ROOT, "data", "box_a")
try:
    from src.adapters.box_a_manager import BoxAManager
    _box_a_mgr = BoxAManager(store_dir=_DATA_DIR_A)
    _ba_docs = _box_a_mgr.list_documents()
    _ba_active = sum(1 for d in _ba_docs if d["status"] == "active")
    print(f"[UI] Box A Manager loaded: {len(_ba_docs)} documents ({_ba_active} active)")
except Exception as e:
    print(f"[UI] Box A Manager unavailable: {e}")

# Phase G.11 — real Box B / Box C reserved document-slot backends.
_box_b_mgr = None
_box_c_mgr = None
_DATA_DIR_B = os.path.join(ROOT, "data", "box_b")
_DATA_DIR_C = os.path.join(ROOT, "data", "box_c")
try:
    from src.adapters.box_b_manager import BoxBManager
    _box_b_mgr = BoxBManager(store_dir=_DATA_DIR_B)
    _bb_docs = _box_b_mgr.list_documents()
    _bb_active = sum(1 for d in _bb_docs if d["status"] == "active")
    print(f"[UI] Box B Manager loaded: {len(_bb_docs)} documents ({_bb_active} active)")
except Exception as e:
    print(f"[UI] Box B Manager unavailable: {e}")
try:
    from src.adapters.box_c_manager import BoxCManager
    _box_c_mgr = BoxCManager(store_dir=_DATA_DIR_C)
    _bc_docs = _box_c_mgr.list_documents()
    _bc_active = sum(1 for d in _bc_docs if d["status"] == "active")
    print(f"[UI] Box C Manager loaded: {len(_bc_docs)} documents ({_bc_active} active)")
except Exception as e:
    print(f"[UI] Box C Manager unavailable: {e}")

_engine = RoutingEngine(
    adapter=_adapter,
    web_search_adapter=_web_search,
    kiwix_adapter=_kiwix,
    box_0_adapter=_box_0,
    wiki_adapter=_wiki,
    box_a_manager=_box_a_mgr,
    box_b_manager=_box_b_mgr,
    box_c_manager=_box_c_mgr,
)

# Phase G.11 — expose the UI's engine to the API server, so a process
# that launches both surfaces shares a single RoutingEngine.
try:
    from src.app.api import set_engine as _api_set_engine
    _api_set_engine(_engine)
except Exception:
    pass

# ── Startup connectivity checks ─────────────────────────────────────────────

def _startup_checks():
    ok = True
    web_api_key = os.environ.get("BRAVE_API_KEY", "")
    if not web_api_key:
        print("[STARTUP] WEB_API_KEY is empty — web search will fail")
        ok = False
    else:
        print(f"[STARTUP] WEB_API_KEY loaded ({len(web_api_key)} chars)")
    if web_api_key:
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://api.search.brave.com/res/v1/web/search?q=test",
                headers={"X-Subscription-Token": web_api_key}
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                print(f"[STARTUP] Web search API reachable (HTTP {r.status})")
        except Exception as e:
            print(f"[STARTUP] Web search API unreachable: {e}")
            ok = False
    kiwix_port = os.environ.get("KIWIX_PORT", "8888")
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://localhost:{kiwix_port}/", timeout=3) as r:
            print(f"[STARTUP] Kiwix reachable on port {kiwix_port}")
    except Exception as e:
        print(f"[STARTUP] Kiwix not reachable on port {kiwix_port}: {e}")
        ok = False
    if ok:
        print("[STARTUP] All checks passed")
    else:
        print("[STARTUP] Some checks failed — see above")

_startup_checks()

# ── Box A helpers ──────────────────────────────────────────────────────────
_CORPUS_DIR = os.path.join(ROOT, "corpus")
_UPLOAD_EXTENSIONS = {
    ".md", ".txt", ".rst", ".csv",
    ".docx", ".xlsx", ".pptx", ".pdf",
    ".py", ".js", ".json", ".yaml", ".yml",
    ".html", ".xml",
}


def _list_box_a_docs() -> str:
    if _box_a_mgr is None:
        return "(Box A not available)"
    docs = _box_a_mgr.list_documents()
    if not docs:
        return "(no documents)"
    lines = []
    for d in docs:
        icon = "✅" if d["status"] == "active" else "⏸"
        lines.append(f"- {icon} {d['filename']} ({d['chunk_count']} chunks)")
    return "\n".join(lines)


def _get_box_a_choices() -> list:
    if _box_a_mgr is None:
        return []
    docs = _box_a_mgr.list_documents()
    choices = []
    for d in docs:
        icon = "✅" if d["status"] == "active" else "⏸"
        label = f"{icon} {d['filename']} ({d['chunk_count']} chunks)"
        choices.append((label, d["doc_id"]))
    return choices


def _handle_upload(file_obj) -> tuple:
    if _box_a_mgr is None:
        return "Box A not available.", _list_box_a_docs(), gr.update(choices=[])
    if file_obj is None:
        return "No file selected.", _list_box_a_docs(), gr.update(choices=_get_box_a_choices())
    src_path = file_obj if isinstance(file_obj, str) else file_obj.name
    fname = os.path.basename(src_path)
    ext = os.path.splitext(fname)[1].lower()
    if ext not in _UPLOAD_EXTENSIONS:
        return (
            f"Unsupported: {ext}\nSupported: {', '.join(sorted(_UPLOAD_EXTENSIONS))}",
            _list_box_a_docs(),
            gr.update(choices=_get_box_a_choices()),
        )
    try:
        result = _box_a_mgr.add_document(src_path, fname)
        if result.get("error"):
            return f"Error: {result['error']}", _list_box_a_docs(), gr.update(choices=_get_box_a_choices())
        return (
            f"Added: {fname} ({result['chunk_count']} chunks)",
            _list_box_a_docs(),
            gr.update(choices=_get_box_a_choices()),
        )
    except Exception as e:
        return f"Upload failed: {e}", _list_box_a_docs(), gr.update(choices=_get_box_a_choices())


def _handle_toggle(doc_id) -> tuple:
    if _box_a_mgr is None or not doc_id:
        return "No document selected.", _list_box_a_docs(), gr.update(choices=_get_box_a_choices())
    new_status = _box_a_mgr.toggle_document(doc_id)
    return (
        f"Document {doc_id}: {new_status}",
        _list_box_a_docs(),
        gr.update(choices=_get_box_a_choices()),
    )


def _handle_delete(doc_id) -> tuple:
    if _box_a_mgr is None or not doc_id:
        return "No document selected.", _list_box_a_docs(), gr.update(choices=_get_box_a_choices())
    _box_a_mgr.remove_document(doc_id)
    return (
        f"Deleted: {doc_id}",
        _list_box_a_docs(),
        gr.update(choices=_get_box_a_choices(), value=None),
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _trace_md(result: RoutingResult) -> str:
    ap  = result.appraisal
    dec = result.decision
    lines = []
    lines.append("**Route decision**")
    lines.append(f"- Route: `{dec.route}`")
    if getattr(dec, "answer_shape", None):
        lines.append(f"- Answer shape: `{dec.answer_shape}`")
    lines.append("\n**Appraisal**")
    for attr, label in [
        ("completeness",        "Completeness"),
        ("uncertainty",         "Uncertainty"),
        ("freshness_sensitive", "Freshness-sensitive"),
        ("safety_relevant",     "Safety-relevant"),
        ("intent_clarity",      "Intent clarity"),
        ("stable_fact",         "Stable fact"),
    ]:
        val = getattr(ap, attr, None)
        if val is not None:
            lines.append(f"- {label}: `{val}`")
    kvs = getattr(ap, "kvs", None)
    if kvs:
        lines.append("\n**KVS**")
        for attr in ["tvs", "mkr_eff"]:
            val = getattr(kvs, attr, None)
            if val is not None:
                lines.append(f"- {attr}: `{val:.3f}`")
    if result.sources:
        lines.append("\n**Sources**")
        for s in result.sources[:5]:
            lines.append(f"- {s}")
    if result.trace:
        lines.append("\n**Pipeline trace**")
        lines.append("```json")
        lines.append(json.dumps(result.trace, ensure_ascii=False, indent=2)[:1500])
        lines.append("```")
    return "\n".join(lines)


def _export_md(result: RoutingResult, query: str) -> str:
    ts = datetime.datetime.now().isoformat()
    return "\n".join([
        "# MOBIUS Audit Export",
        f"**Query**: {query}",
        f"**Timestamp**: {ts}",
        f"**Route**: {result.decision.route}",
        f"**Response**:\n{result.response_text}",
        "",
        _trace_md(result),
    ])


def _export_json(result: RoutingResult, query: str) -> str:
    ap  = result.appraisal
    kvs = getattr(ap, "kvs", None)
    return json.dumps({
        "query":     query,
        "timestamp": datetime.datetime.now().isoformat(),
        "route":     result.decision.route,
        "response":  result.response_text,
        "appraisal": {
            "completeness":        getattr(ap, "completeness", None),
            "uncertainty":         getattr(ap, "uncertainty", None),
            "freshness_sensitive": getattr(ap, "freshness_sensitive", None),
            "safety_relevant":     getattr(ap, "safety_relevant", None),
            "intent_clarity":      getattr(ap, "intent_clarity", None),
            "stable_fact":         getattr(ap, "stable_fact", None),
            "kvs_tvs":             getattr(kvs, "tvs", None) if kvs else None,
            "kvs_mkr_eff":         getattr(kvs, "mkr_eff", None) if kvs else None,
        },
        "sources": result.sources[:5],
        "trace":   result.trace,
    }, ensure_ascii=False, indent=2)


def _build_right_summary(result, mobius_on: bool):
    """Build (one_line_summary, detail_text) from a RoutingResult."""
    if not mobius_on or result is None:
        return ("-- RAW mode", "Route: RAW (MOBIUS OFF)\nNo trace available.")

    route = result.decision.route
    trace = result.trace or {}
    ap    = result.appraisal
    kvs   = getattr(ap, "kvs", None)
    tvs   = getattr(kvs, "tvs", 0) if kvs else 0
    mkr   = getattr(kvs, "mkr_eff", 0) if kvs else 0
    admissibility = trace.get("Admissibility", "N/A")
    verify_outcome = trace.get("VerifyOutcome", "")
    sources_list = trace.get("Sources") or []

    # Classify sources
    src_types = set()
    for s in (sources_list if isinstance(sources_list, list) else []):
        name = s.get("source_name", "") if isinstance(s, dict) else str(s)
        nl = name.lower()
        if "wikipedia" in nl or "kiwix" in nl:
            src_types.add("Wikipedia")
        elif "brave" in nl or "web" in nl:
            src_types.add("Web search")
        elif "box_a" in nl or "local" in nl or "file://" in nl:
            src_types.add("uploaded doc")
        else:
            src_types.add(name[:20] if name else "unknown")
    src_label = " + ".join(sorted(src_types)) if src_types else "no source"

    # Build 1-line summary
    if route == "answer":
        summary = f"answer -- model knowledge"
    elif route == "verify":
        if verify_outcome == "verify_success":
            summary = f"answer -- {src_label}"
        elif verify_outcome == "verify_partial":
            summary = f"bounded -- {src_label}"
        else:
            summary = f"verify failed -- {src_label}"
    elif route == "ask":
        summary = f"? ask -- under-specified"
    elif route == "abstain":
        summary = f"abstain -- safety limit"
    else:
        summary = f"{route}"

    # TVS label
    if tvs >= 0.6:
        tvs_label = "high-volatility"
    elif tvs < 0.3:
        tvs_label = "stable"
    else:
        tvs_label = "moderate"
    mkr_label = "reliable" if mkr >= 0.5 else "unreliable"

    # Build detail
    halfstep = getattr(result.decision, "answer_shape", None) or "N/A"
    ks = trace.get("KnowledgeSource", "N/A")
    ks_label = {
        "retrieved": "retrieved (source-backed)",
        "model": "model (no relevant sources found)",
        "mixed": "mixed (source + model knowledge)",
        "none": "none",
    }.get(ks, ks)
    _pass_mode = "dual (GPU0→GPU1)" if (_adapter and getattr(_adapter, 'dual_pass', False)) else "single"
    # Box A info
    box_a_mode = trace.get("BoxA_mode")
    box_a_fnames = trace.get("BoxA_filenames", [])
    box_a_score = trace.get("BoxA_top_score")
    box_a_compliant = trace.get("BoxA_compliant")
    if box_a_mode:
        box_a_label = f"{box_a_mode} mode ({box_a_fnames[0] if box_a_fnames else '?'}, score: {box_a_score:.2f})"
    else:
        box_a_label = "N/A"
    qk41_label = ""
    if box_a_mode in ("RULE", "CRITERIA"):
        qk41_label = "COMPLIANT" if box_a_compliant else "VIOLATION (corrected)"

    trace_lines = [
        f"Route:          {route}",
        f"admissibility:  {admissibility}",
        f"Knowledge:      {ks_label}",
        f"Pass:           {_pass_mode}",
        f"TVS:            {tvs:.2f}  ({tvs_label})",
        f"MKR:            {mkr:.2f}  ({mkr_label})",
        f"HalfStep:       {halfstep}",
        f"Box A:          {box_a_label}",
    ]
    if qk41_label:
        trace_lines.append(f"QK_41:          {qk41_label}")
    detail = "```\n" + "\n".join(trace_lines) + "\n```"
    if sources_list:
        source_lines = ["**Sources:**"]
        for i, s in enumerate(sources_list[:5], 1):
            if isinstance(s, dict):
                url = s.get('url', '')
                name = s.get('source_name', '')
                title = s.get('title', '')
                if url and "localhost:8888" in url:
                    label = url.split("/")[-1].replace("%3A", ":").replace("_", " ")[:40]
                    source_lines.append(f"- {name} — [{label}]({url})")
                elif url:
                    source_lines.append(f"- {name} — [{title[:40]}]({url})")
                else:
                    source_lines.append(f"- {name} — {title}")
            else:
                source_lines.append(f"- {s}")
        detail += "\n\n" + "\n".join(source_lines)
    return summary, detail


# ── Main processing ──────────────────────────────────────────────────────────

def process(query, history, session_data, mobius_on, explore_on, tz_setting="UTC"):
    if not query or not query.strip():
        return history, session_data, "", "", "", ""

    _tz = tz_setting if tz_setting and tz_setting != "auto" else "UTC"
    session = session_data.get("session") or SessionState()
    # Attach persistent M-2/M-3 to session
    if not hasattr(session, 'verified_facts') or not session.verified_facts.facts:
        session.verified_facts = _m3_facts
    if not hasattr(session, 'user_profile'):
        session.user_profile = _m2_profile
    conv_turns = getattr(session, "conversation_turns", [])

    if mobius_on:
        # ── MOBIUS governed mode ─────────────────────────────────────
        if _adapter is not None:
            _adapter._conversation_turns = conv_turns[-6:] if conv_turns else []
            # QK injection: select metacognitive kernels based on intent
            try:
                from src.adapters.question_kernel import (
                    select_kernels, format_kernel_block, get_zone_for_intent
                )
                _qk_zone = get_zone_for_intent("factual_query")  # default
                _qk_kernels = select_kernels("factual_query", zone=_qk_zone)
                _qk_block = format_kernel_block(_qk_kernels)
                _adapter._governance_instruction = _qk_block
            except Exception:
                _adapter._governance_instruction = ""
        try:
            result = _engine.evaluate(query, session_state=session)
        except Exception as e:
            err = f"[Engine error: {e}]"
            history = history + [{"role": "user", "content": query},
                                  {"role": "assistant", "content": err}]
            return history, session_data, "", "", "", ""
        finally:
            if _adapter is not None:
                _adapter._governance_instruction = ""

        resp  = result.response_text or "(no response)"
        trace = _trace_md(result)
        r_summary, r_detail = _build_right_summary(result, True)

        conv_turns.append({"role": "user", "content": query})
        conv_turns.append({"role": "assistant", "content": resp})
        if len(conv_turns) > 20:
            session.conversation_turns = conv_turns[-20:]

        # M-1: Extract entities from completed turn
        if hasattr(session, 'instant_memory'):
            session.extract_entities_from_turn(query, resp)

        # M-3: Persist if facts were stored during verify
        if hasattr(session, 'verified_facts') and session.verified_facts.facts:
            _save_verified_facts(session.verified_facts)

        _ts = _format_ts(_tz)
        history = history + [{"role": "user", "content": f"{_ts} {query}"},
                              {"role": "assistant", "content": f"{_ts} {resp}"}]
        # Record trace history
        th = session_data.get("trace_history", []) if session_data else []
        th.append({
            "turn": len(th) + 1,
            "query": query[:50] + ("..." if len(query) > 50 else ""),
            "detail": r_detail,
        })
        session_data = {
            "session": session, "last_result": result, "last_query": query,
            "mode": "MOBIUS ON", "trace_history": th,
        }
        # Phase G.6: natural automatic checkpoint trigger.
        # Runs AFTER the user-facing response has been rendered — this is
        # the natural low-risk post-response hook. It is cheap (O(1)
        # scanning bounded lists) and uses a turn-interval debounce so
        # it does not fire on every single turn. Opt-out is honored.
        #
        # Phase G.7: after a successful checkpoint refresh, consider
        # conservative auto-promotion. The policy (two-hit rule + adopted
        # signal dominance + stricter confidence) lives in
        # `maybe_auto_promote`; most calls short-circuit cheaply.
        #
        # Phase G.9: when the appraisal flags continuity_save_intent
        # ("今までの話を保存したい" / "save this conversation"), also
        # invoke the existing manual-carryover path. Opt-out still
        # blocks promotion; the UI pending chip reflects the result.
        try:
            from src.memory.carryover import (
                maybe_checkpoint, maybe_auto_promote,
                trigger_manual_checkpoint,
            )
            maybe_checkpoint(session)
            maybe_auto_promote(session)
            if getattr(result, "appraisal", None) is not None and \
                    getattr(result.appraisal, "continuity_save_intent", False):
                _profile = session.ensure_box_p()
                trigger_manual_checkpoint(
                    session, promote=True, profile=_profile,
                    language=getattr(session, "active_language", None),
                )
                # Inspectable reason_code (G.9).
                if "CONTINUITY_MANUAL_SAVE_TRIGGERED" \
                        not in result.decision.reason_codes:
                    result.decision.reason_codes.append(
                        "CONTINUITY_MANUAL_SAVE_TRIGGERED"
                    )
        except Exception:   # noqa: BLE001
            pass
        return history, session_data, "", trace, r_summary, r_detail

    else:
        # ── RAW LLM mode (MOBIUS OFF) ────────────────────────────────
        if _adapter is None:
            history = history + [{"role": "user", "content": query},
                                  {"role": "assistant", "content": "[No adapter available]"}]
            return history, session_data, "", "", "-- RAW mode", ""

        # M-2: Apply explanation depth
        depth_note = ""
        if hasattr(session, 'user_profile'):
            depth_note = session.user_profile.apply_to_prompt()

        if explore_on:
            prompt = (
                f"Think step by step and explore this question thoroughly.\n\n"
                f"Question: {query}\n\nAnswer:"
            )
        else:
            prompt = f"Question: {query}\n\nAnswer concisely:"
        if depth_note:
            prompt = depth_note + "\n\n" + prompt

        try:
            from src.compose.prompt_builder import build_raw_mode_instruction
            _adapter._governance_instruction = build_raw_mode_instruction(explore_on)
            req = KernelRequest(
                user_input=query, prompt=prompt,
                metadata={"conversation_turns": conv_turns} if conv_turns else {},
            )
            resp = _adapter.generate(req)
            text = resp.text or "(empty response)"
        except Exception as e:
            text = f"[Error: {e}]"
        finally:
            if _adapter is not None:
                _adapter._governance_instruction = ""

        conv_turns.append({"role": "user", "content": query})
        conv_turns.append({"role": "assistant", "content": text})
        if len(conv_turns) > 20:
            session.conversation_turns = conv_turns[-20:]

        _ts = _format_ts(_tz)
        history = history + [{"role": "user", "content": f"{_ts} {query}"},
                              {"role": "assistant", "content": f"{_ts} {text}"}]
        session_data = {
            "session": session, "last_result": None, "last_query": query,
            "mode": "RAW",
        }
        return history, session_data, "", "", "-- RAW mode", "Route: RAW (MOBIUS OFF)\nNo trace available."


def process_stream(query, history, session_data, mobius_on, explore_on, tz_setting="UTC"):
    """Streaming version of process(). Yields 6-tuple progressively."""
    if not query or not query.strip():
        yield history, session_data, "", "", "", ""
        return

    # Resolve timezone label to IANA name
    _tz_map = {label: val for label, val in _TZ_CHOICES}
    _tz = _tz_map.get(tz_setting, tz_setting)
    if _tz == "auto":
        _tz = "UTC"

    session = session_data.get("session") or SessionState()
    if not hasattr(session, 'verified_facts') or not session.verified_facts.facts:
        session.verified_facts = _m3_facts
    if not hasattr(session, 'user_profile'):
        session.user_profile = _m2_profile
    conv_turns = getattr(session, "conversation_turns", [])

    if mobius_on:
        # ── MOBIUS governed mode (streaming) ─────────────────────────
        if _adapter is not None:
            _adapter._conversation_turns = conv_turns[-6:] if conv_turns else []
            try:
                from src.adapters.question_kernel import (
                    select_kernels, format_kernel_block, get_zone_for_intent
                )
                _qk_zone = get_zone_for_intent("factual_query")
                _qk_kernels = select_kernels("factual_query", zone=_qk_zone)
                _qk_block = format_kernel_block(_qk_kernels)
                _adapter._governance_instruction = _qk_block
            except Exception:
                _adapter._governance_instruction = ""

        try:
            if hasattr(_engine, 'evaluate_stream') and _adapter is not None:
                # Add user message, show typing indicator
                streaming_history = history + [
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": ""},
                ]
                yield streaming_history, session_data, "", "", "", ""

                # Stream tokens
                partial = ""
                for token in _engine.evaluate_stream(query, session_state=session):
                    partial += token
                    streaming_history = history + [
                        {"role": "user", "content": query},
                        {"role": "assistant", "content": partial},
                    ]
                    yield streaming_history, session_data, "", "", "", ""

                resp = partial or "(no response)"
                r_summary = "-- streamed"
                r_detail = ""
                trace = ""

                # Try to get trace from last result if available
                last_result = getattr(session, '_last_eval_result', None)
                if last_result:
                    trace = _trace_md(last_result)
                    r_summary, r_detail = _build_right_summary(last_result, True)
            else:
                # Fallback to non-streaming
                result = _engine.evaluate(query, session_state=session)
                resp = result.response_text or "(no response)"
                trace = _trace_md(result)
                r_summary, r_detail = _build_right_summary(result, True)

        except Exception as e:
            resp = f"[Engine error: {e}]"
            trace, r_summary, r_detail = "", "", ""
        finally:
            if _adapter is not None:
                _adapter._governance_instruction = ""

        conv_turns.append({"role": "user", "content": query})
        conv_turns.append({"role": "assistant", "content": resp})
        if len(conv_turns) > 20:
            session.conversation_turns = conv_turns[-20:]

        if hasattr(session, 'instant_memory'):
            session.extract_entities_from_turn(query, resp)
        if hasattr(session, 'verified_facts') and session.verified_facts.facts:
            _save_verified_facts(session.verified_facts)

        _ts = _format_ts(_tz)
        final_history = history + [
            {"role": "user", "content": f"{_ts} {query}"},
            {"role": "assistant", "content": f"{_ts} {resp}"},
        ]
        # Record trace history
        th = session_data.get("trace_history", []) if session_data else []
        th.append({
            "turn": len(th) + 1,
            "query": query[:50] + ("..." if len(query) > 50 else ""),
            "detail": r_detail,
        })
        session_data = {
            "session": session, "last_result": None, "last_query": query,
            "mode": "MOBIUS ON", "trace_history": th,
        }
        yield final_history, session_data, "", trace, r_summary, r_detail

    else:
        # ── RAW LLM mode (streaming) ────────────────────────────────
        if _adapter is None:
            history = history + [{"role": "user", "content": query},
                                  {"role": "assistant", "content": "[No adapter available]"}]
            yield history, session_data, "", "", "-- RAW mode", ""
            return

        depth_note = ""
        if hasattr(session, 'user_profile'):
            depth_note = session.user_profile.apply_to_prompt()

        if explore_on:
            prompt = f"Think step by step and explore this question thoroughly.\n\nQuestion: {query}\n\nAnswer:"
        else:
            prompt = f"Question: {query}\n\nAnswer concisely:"
        if depth_note:
            prompt = depth_note + "\n\n" + prompt

        try:
            from src.compose.prompt_builder import build_raw_mode_instruction
            _adapter._governance_instruction = build_raw_mode_instruction(explore_on)
            req = KernelRequest(
                user_input=query, prompt=prompt,
                metadata={"conversation_turns": conv_turns, "intent_type": "factual_query", "route": "answer"} if conv_turns else {"intent_type": "factual_query", "route": "answer"},
            )

            if hasattr(_adapter, 'generate_stream'):
                streaming_history = history + [
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": ""},
                ]
                yield streaming_history, session_data, "", "", "-- RAW mode", ""

                partial = ""
                for token in _adapter.generate_stream(req):
                    partial += token
                    streaming_history = history + [
                        {"role": "user", "content": query},
                        {"role": "assistant", "content": partial},
                    ]
                    yield streaming_history, session_data, "", "", "-- RAW mode", ""
                text = partial or "(empty response)"
            else:
                resp = _adapter.generate(req)
                text = resp.text or "(empty response)"
        except Exception as e:
            text = f"[Error: {e}]"
        finally:
            if _adapter is not None:
                _adapter._governance_instruction = ""

        conv_turns.append({"role": "user", "content": query})
        conv_turns.append({"role": "assistant", "content": text})
        if len(conv_turns) > 20:
            session.conversation_turns = conv_turns[-20:]

        _ts = _format_ts(_tz)
        final_history = history + [
            {"role": "user", "content": f"{_ts} {query}"},
            {"role": "assistant", "content": f"{_ts} {text}"},
        ]
        # Record trace history for RAW mode
        th = session_data.get("trace_history", []) if session_data else []
        raw_detail = "Route: RAW (MOBIUS OFF)\nNo trace available."
        th.append({
            "turn": len(th) + 1,
            "query": query[:50] + ("..." if len(query) > 50 else ""),
            "detail": raw_detail,
        })
        session_data = {
            "session": session, "last_result": None, "last_query": query,
            "mode": "RAW", "trace_history": th,
        }
        yield final_history, session_data, "", "", "-- RAW mode", raw_detail


def _format_conversation_plain(chatbot_history, session_data):
    """Build plain text from full chatbot history."""
    if not chatbot_history:
        return "(no conversation)"
    lines = []
    for msg in chatbot_history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            lines.append(f"Assistant: {content}")
    # Append audit summary if MOBIUS mode
    result = (session_data or {}).get("last_result")
    if result is not None:
        lines.append("")
        lines.append("--- Audit (last turn) ---")
        lines.append(f"Route: {result.decision.route}")
        if result.sources:
            lines.append(f"Sources: {', '.join(str(s) for s in result.sources[:5])}")
    return "\n\n".join(lines)


def do_copy_conversation(chatbot_history, session_data):
    text = _format_conversation_plain(chatbot_history, session_data)
    return text, '<span style="color:#1D9E75;font-weight:600;">Copied!</span>'


def do_export_md(chatbot_history, session_data):
    if not chatbot_history:
        return "(no conversation)"
    ts = datetime.datetime.now().isoformat()
    mode = (session_data or {}).get("mode", "unknown")
    lines = [
        "# MOBIUS Conversation Export",
        f"**Timestamp**: {ts}",
        f"**Mode**: {mode}",
        "",
    ]
    for msg in chatbot_history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lines.append(f"**User**: {content}")
        elif role == "assistant":
            lines.append(f"**Assistant**: {content}")
        lines.append("")

    # Audit trace for last turn (MOBIUS ON)
    result = (session_data or {}).get("last_result")
    if result is not None:
        lines.append("---")
        lines.append("")
        lines.append("## Audit Trace (last turn)")
        lines.append("")
        lines.append(_trace_md(result))
    return "\n".join(lines)


def do_export_json(chatbot_history, session_data):
    if not chatbot_history:
        return "{}"
    mode = (session_data or {}).get("mode", "unknown")
    turns = []
    for msg in chatbot_history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role in ("user", "assistant"):
            turns.append({"role": role, "content": content})

    export = {
        "timestamp": datetime.datetime.now().isoformat(),
        "mode": mode,
        "turns": turns,
    }
    # Include audit for last turn
    result = (session_data or {}).get("last_result")
    if result is not None:
        ap  = result.appraisal
        kvs = getattr(ap, "kvs", None)
        export["last_turn_audit"] = {
            "route":     result.decision.route,
            "appraisal": {
                "completeness":        getattr(ap, "completeness", None),
                "uncertainty":         getattr(ap, "uncertainty", None),
                "freshness_sensitive": getattr(ap, "freshness_sensitive", None),
                "safety_relevant":     getattr(ap, "safety_relevant", None),
                "intent_clarity":      getattr(ap, "intent_clarity", None),
                "stable_fact":         getattr(ap, "stable_fact", None),
                "kvs_tvs":             getattr(kvs, "tvs", None) if kvs else None,
                "kvs_mkr_eff":         getattr(kvs, "mkr_eff", None) if kvs else None,
            },
            "sources": result.sources[:5],
            "trace":   result.trace,
        }
    return json.dumps(export, ensure_ascii=False, indent=2)


def clear_all():
    return [], {}, "", "", "", ""


def get_mode_status(mobius_on, explore_on):
    m = "ON" if mobius_on else "OFF"
    e = "ON" if explore_on else "OFF"
    t = "ON (think:True)" if explore_on else "OFF (think:False)"
    retrieval = "Box0 + BoxA + BoxW + Kiwix + BoxS/Brave" if mobius_on else "None (direct LLM)"
    return (
        f"MOBIUS:     {m}\n"
        f"Explore:    {e}\n"
        f"Thinking:   {t}\n"
        f"Model:      qwen3.5:9b\n"
        f"Retrieval:  {retrieval}"
    )


# ── UI definition ────────────────────────────────────────────────────────────

CSS = """
footer { display: none !important; }
.settings-hint { color: #888; font-size: 0.85em; font-style: italic; }
.right-summary { font-size: 0.95em; font-weight: 600; padding: 6px 0; }
.mobius-footer { text-align: center; color: #666; font-size: 0.8em; padding: 8px 0 4px 0; border-top: 1px solid #333; margin-top: 8px; }
"""

COPY_JS = """
async () => {
    const el = document.querySelector('#mobius-export textarea');
    if (!el || !el.value.trim()) { return; }
    try {
        await navigator.clipboard.writeText(el.value);
    } catch (err) {
        const ta = document.createElement('textarea');
        ta.value = el.value;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
    }
}
"""

COPY_RESET_JS = """
() => { setTimeout(() => {
    const el = document.getElementById('copy-feedback');
    if (el) el.innerHTML = '';
}, 2000); }
"""

with gr.Blocks(title="MOBIUS MMV", css=CSS) as demo:

    session_state = gr.State({})
    mobius_state  = gr.State(True)
    explore_state = gr.State(False)
    export_ext    = gr.State("txt")  # tracks last export type: txt, md, json
    trace_history = gr.State([])     # List[dict] for turn history

    # ── Two-column layout ────────────────────────────────────────────
    with gr.Row():
        # Left column: clean chat
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(
                height=480, layout="bubble", render_markdown=True, show_label=False,
            )

        # Right column: MOBIUS judgment summary
        with gr.Column(scale=1):
            right_summary = gr.Textbox(
                value="", show_label=False, interactive=False, lines=1,
                elem_classes=["right-summary"],
            )
            with gr.Accordion("Detail", open=False):
                turn_selector = gr.Dropdown(
                    label="Turn History", choices=[], value=None,
                    interactive=True,
                )
                right_detail = gr.Markdown(
                    value="", show_label=False,
                )

    # ── Input row ────────────────────────────────────────────────────
    with gr.Row():
        query_box = gr.Textbox(
            placeholder="Enter your query...",
            show_label=False, scale=6, lines=1,
        )
        send_btn = gr.Button("Send", variant="primary", scale=1)

    # ── Settings ─────────────────────────────────────────────────────
    with gr.Accordion("Settings", open=False):

        with gr.Row():
            gr.Markdown("**MOBIUS**")
            mobius_on_btn  = gr.Button("ON",  variant="primary",   scale=1, min_width=60)
            mobius_off_btn = gr.Button("OFF", variant="secondary", scale=1, min_width=60)
            gr.Markdown("**Explore**")
            explore_on_btn  = gr.Button("ON",  variant="secondary", scale=1, min_width=60)
            explore_off_btn = gr.Button("OFF", variant="primary",   scale=1, min_width=60)

        with gr.Row():
            tz_dropdown = gr.Dropdown(
                label="Timezone",
                choices=[label for label, _ in _TZ_CHOICES],
                value="Auto (Browser)",
                interactive=True,
                scale=2,
            )

        gr.Markdown("---")

        with gr.Accordion("Current mode status", open=False):
            mode_display = gr.Textbox(
                value=get_mode_status(True, False),
                interactive=False, lines=5, show_label=False,
            )

        with gr.Accordion("Audit / Log", open=False):
            with gr.Accordion("View trace", open=False):
                trace_out = gr.Markdown()
            with gr.Row():
                copy_btn = gr.Button("Copy conversation", scale=1)
                copy_feedback = gr.HTML(value="", elem_id="copy-feedback")
            with gr.Row():
                md_btn   = gr.Button("Save MD", scale=1)
                json_btn = gr.Button("Save JSON", scale=1)
            export_out = gr.Textbox(label="Export", lines=8, interactive=False, elem_id="mobius-export")
            with gr.Row():
                export_dl_btn = gr.Button("Export ↓ Download", scale=1)
                export_file   = gr.File(label="Download")

        # ── Phase G.5 / G.6: carryover control + pending visibility ───
        # Natural replacement for the retired end-of-session save modal.
        # Default = allowed. When the opt-out toggle is ON, this session
        # will NOT contribute to future continuity (Box P). Active-session
        # M behavior is unaffected.
        with gr.Row():
            carryover_opt_out_toggle = gr.Checkbox(
                label="Do not carry this conversation forward",
                value=False,
                info="When on, this conversation will not contribute to future continuity.",
                scale=3,
            )
            carryover_status_chip = gr.Textbox(
                label="Carryover",
                value="On",
                interactive=False,
                lines=1,
                scale=1,
            )
        # Phase G.6 / G.7: continuity status + manual save.
        # The chip shows a calm, user-friendly label derived from the
        # canonical `presentation_status()`. The save button is enabled
        # only when the pending candidate is actually promotable. The
        # help text gives a one-line human explanation of the current
        # state. Wording intentionally avoids Box P internals.
        with gr.Row():
            carryover_pending_chip = gr.Textbox(
                label="Continuity",
                value="Not ready",
                interactive=False,
                lines=1,
                scale=2,
            )
            carryover_save_btn = gr.Button(
                "Save continuity now",
                variant="secondary",
                scale=1,
                interactive=False,
            )
        carryover_help_md = gr.Markdown(
            value="Nothing to carry forward yet.",
            elem_classes=["settings-hint"],
        )

        with gr.Row():
            boxm_save_btn = gr.Button("💾 Save Session Memory", variant="secondary", scale=1)
            boxm_load_btn = gr.Button("📂 Load Session Memory", variant="secondary", scale=1)
            boxm_status   = gr.Textbox(label="Box M", interactive=False, lines=1, scale=2)
        with gr.Row(visible=False) as boxm_load_row:
            boxm_snapshot_dd = gr.Dropdown(label="Select snapshot", choices=[], scale=3)
            boxm_import_btn  = gr.Button("Import", variant="primary", scale=1)

        with gr.Accordion("Documents (Box A)", open=False):
            doc_list = gr.Markdown(value=_list_box_a_docs())
            upload_file = gr.File(
                label="Upload document",
                file_types=[e for e in sorted(_UPLOAD_EXTENSIONS)],
            )
            with gr.Row():
                box_a_selector = gr.Dropdown(
                    label="Select document",
                    choices=_get_box_a_choices(),
                    interactive=True,
                )
                box_a_toggle_btn = gr.Button("⏸ Enable/Disable", variant="secondary", scale=1)
                box_a_delete_btn = gr.Button("🗑 Delete", variant="stop", scale=1)
            upload_status = gr.Textbox(label="Status", interactive=False, lines=1)

        # Phase G.11/G.12 — advanced Box B / Box C / Profile controls.
        # Kept behind a collapsed accordion so the calm default UX is
        # preserved. Box B / C are reserved document slots governed by
        # the active authority
        # profile's reserved_boxes_allowed flag; uploads persist to
        # data/box_b/ and data/box_c/ respectively.
        #
        # Phase G.12: improved empty-state UX. When a manager is loaded
        # but has no active documents, the UI communicates "dormant but
        # available — upload to activate", not "broken". When the
        # manager itself is absent (unavailable), a different "not
        # available" label is shown so the user can tell them apart.
        with gr.Accordion("Advanced: Profiles & Reserved Boxes (B / C)", open=False):
            gr.Markdown(
                "**Box B** = reserved project document slot. "
                "**Box C** = reserved archive / cold document slot. "
                "Active only when the selected profile allows reserved boxes "
                "(e.g. `wide_recall`). Both boxes are **optional**; empty "
                "stores do not produce content and do not break anything — "
                "they stay dormant until you upload a document."
            )
            # Authority profile selector.
            profile_dropdown = gr.Dropdown(
                label="Authority profile",
                choices=[
                    "balanced_default",
                    "memory_first",
                    "workspace_first",
                    "verify_heavy",
                    "wide_recall",
                ],
                value="balanced_default",
                interactive=True,
                info="Changes which boxes and signals take precedence in routing. "
                     "`wide_recall` also enables Box B / C.",
            )
            profile_status = gr.Textbox(
                label="Active profile",
                value="balanced_default",
                interactive=False,
                lines=1,
            )
            gr.Markdown("---")

            # Phase G.12 — empty-state helpers.
            def _box_doc_listing(mgr, label):
                """Return a compact Markdown list of documents for a
                Box B/C reserved-slot manager, or a clear empty-state message."""
                if mgr is None:
                    return (
                        f"⚪ **Box {label} not available** — the backend "
                        f"could not be loaded. Check `data/box_{label.lower()}/` "
                        f"directory permissions or see startup logs."
                    )
                try:
                    docs = mgr.list_documents()
                except Exception:
                    docs = []
                active = [d for d in docs if d.get("status") == "active"]
                if not docs:
                    return (
                        f"📭 **Box {label} is empty** — no documents yet.\n\n"
                        f"Upload a file below to activate Box {label}. "
                        f"(Active only when a profile that allows reserved "
                        f"boxes is selected, e.g. `wide_recall`.)"
                    )
                lines = [
                    f"📂 **Box {label}: {len(active)} active / "
                    f"{len(docs)} total**",
                    "",
                ]
                for d in docs:
                    icon = "✅" if d.get("status") == "active" else "⏸"
                    chunks = d.get("chunk_count", 0)
                    lines.append(
                        f"{icon} {d.get('filename', '(unknown)')} "
                        f"— {chunks} chunks ({d.get('status', '?')})"
                    )
                return "\n".join(lines)

            # Box B panel.
            box_b_doc_list = gr.Markdown(
                value=_box_doc_listing(_box_b_mgr, "B"),
            )
            box_b_upload = gr.File(
                label="Upload to Box B (reserved project documents)",
                file_types=[e for e in sorted(_UPLOAD_EXTENSIONS)],
            )
            box_b_status = gr.Textbox(
                label="Box B status",
                value=(
                    "dormant — upload to activate"
                    if (_box_b_mgr is not None and not _box_b_mgr.has_active_documents())
                    else ("not available" if _box_b_mgr is None else "ready")
                ),
                interactive=False, lines=1,
            )
            gr.Markdown("---")
            # Box C panel.
            box_c_doc_list = gr.Markdown(
                value=_box_doc_listing(_box_c_mgr, "C"),
            )
            box_c_upload = gr.File(
                label="Upload to Box C (reserved archive documents)",
                file_types=[e for e in sorted(_UPLOAD_EXTENSIONS)],
            )
            box_c_status = gr.Textbox(
                label="Box C status",
                value=(
                    "dormant — upload to activate"
                    if (_box_c_mgr is not None and not _box_c_mgr.has_active_documents())
                    else ("not available" if _box_c_mgr is None else "ready")
                ),
                interactive=False, lines=1,
            )
            gr.Markdown("---")
            # Box X — curated external durable knowledge. Read-only
            # status so users can see whether the curated layer is
            # populated. Promotion happens through the S→X pipeline,
            # never from this UI directly.
            gr.Markdown(
                "**Box X** = curated external durable knowledge. "
                "Entries are promoted from Box S via the S→X pipeline "
                "and are separate from Box W (Wikipedia), Box A, and "
                "the reserved Box B/C document slots. This surface is read-only."
            )
            try:
                from src.memory.box_x import BoxXStore as _BoxXStore  # noqa: WPS433
                _box_x_store = _BoxXStore(store_dir=os.path.join(ROOT, "data", "box_x"))
                _bx_stats = _box_x_store.stats()
                _bx_count = _bx_stats.get("entry_count", 0)
                _bx_domains = _bx_stats.get("by_domain", {})
                if _bx_count == 0:
                    _bx_value = "dormant — no entries yet (populate via S→X pipeline)"
                else:
                    _bx_value = (
                        f"{_bx_count} entries across "
                        f"{len(_bx_domains)} domain(s): "
                        f"{', '.join(sorted(_bx_domains.keys())[:5])}"
                    )
            except Exception as _bx_exc:   # noqa: BLE001
                _bx_value = f"not available: {_bx_exc}"
            box_x_status = gr.Textbox(
                label="Box X status",
                value=_bx_value,
                interactive=False,
                lines=1,
            )

            # Box X entry management — list + single-entry deletion.
            # Kept calm: a compact markdown table (no raw content),
            # a dropdown selector for the entry id, and a single
            # delete button. Bulk deletion is intentionally absent.
            from src.memory.box_x import BoxXStore as _BoxXStoreForUI  # noqa: WPS433

            def _box_x_rows():
                try:
                    store = _BoxXStoreForUI(
                        store_dir=os.path.join(ROOT, "data", "box_x"),
                    )
                    return store.list_entries_for_ui()
                except Exception:   # noqa: BLE001
                    return []

            def _render_box_x_table(rows):
                if not rows:
                    return (
                        "📭 **Box X is empty** — no curated external "
                        "entries yet. Populate via the S→X promotion "
                        "pipeline."
                    )
                lines = [
                    "| Title | Domain | Source family | Staleness | entry_id |",
                    "|---|---|---|---|---|",
                ]
                for r in rows:
                    lines.append(
                        f"| {r['title']} | {r['domain']} | "
                        f"{r['source_family']} | {r['staleness_state']} | "
                        f"`{r['entry_id']}` |"
                    )
                return "\n".join(lines)

            def _box_x_choices(rows):
                return [
                    (f"{r['title']} — {r['domain']} ({r['entry_id'][:8]})",
                     r["entry_id"])
                    for r in rows
                ]

            _bx_rows_initial = _box_x_rows()
            box_x_table = gr.Markdown(
                value=_render_box_x_table(_bx_rows_initial),
            )
            box_x_entry_selector = gr.Dropdown(
                label="Select a Box X entry to delete",
                choices=_box_x_choices(_bx_rows_initial),
                interactive=True,
            )
            with gr.Row():
                box_x_refresh_btn = gr.Button(
                    "🔄 Refresh Box X", variant="secondary", scale=1,
                )
                box_x_delete_btn = gr.Button(
                    "🗑 Delete selected Box X entry",
                    variant="stop", scale=1,
                )
            box_x_delete_status = gr.Textbox(
                label="Box X deletion status",
                value="",
                interactive=False, lines=1,
            )

            def _refresh_box_x_ui():
                rows = _box_x_rows()
                return (
                    _render_box_x_table(rows),
                    gr.update(choices=_box_x_choices(rows)),
                    "",
                )

            def _delete_box_x_entry(entry_id):
                if not entry_id:
                    rows = _box_x_rows()
                    return (
                        _render_box_x_table(rows),
                        gr.update(choices=_box_x_choices(rows)),
                        "⚠ Select an entry first.",
                    )
                try:
                    store = _BoxXStoreForUI(
                        store_dir=os.path.join(ROOT, "data", "box_x"),
                    )
                    ok = store.delete_by_entry_id(
                        entry_id,
                        reason="ui_delete",
                        actor="ui",
                    )
                    status = (
                        f"✅ Deleted entry `{entry_id}`."
                        if ok
                        else f"⚠ Entry `{entry_id}` not found."
                    )
                except Exception as exc:   # noqa: BLE001
                    status = f"⚠ Delete failed: {exc}"
                rows = _box_x_rows()
                return (
                    _render_box_x_table(rows),
                    gr.update(choices=_box_x_choices(rows)),
                    status,
                )

            box_x_refresh_btn.click(
                _refresh_box_x_ui,
                inputs=None,
                outputs=[box_x_table, box_x_entry_selector, box_x_delete_status],
            )
            box_x_delete_btn.click(
                _delete_box_x_entry,
                inputs=[box_x_entry_selector],
                outputs=[box_x_table, box_x_entry_selector, box_x_delete_status],
            )

        gr.Markdown(
            "Modes like educational, strict, or concise can be specified in natural language.",
            elem_classes=["settings-hint"],
        )
        gr.Markdown(
            "💡 Explore ONにすると推論精度が向上し応答が簡潔になります。"
            "動作が不安定な場合はOFFに戻してください。",
            elem_classes=["settings-hint"],
        )
        gr.Markdown("---")

        # ── Developer Mode (Super Supervisor) ────────────────────────
        dev_mode_toggle = gr.Checkbox(
            label="Developer Mode",
            value=False,
            info="Enables Super Supervisor diagnostics",
        )
        with gr.Group(visible=False) as dev_panel:
            gr.Markdown(
                "**Super Supervisor**\n\n"
                "The Super Supervisor is a system diagnostic feature "
                "powered by an external LLM. Use of a large-parameter model "
                "or frontier model API is recommended. The model must be "
                "capable of accurately reading the L0 protocol document and "
                "diagnosing behavioral deviations against its standards."
            )
            with gr.Row():
                dev_api_key = gr.Textbox(
                    label="API Key", type="password",
                    placeholder="Groq API key", scale=3,
                )
                dev_model_id = gr.Textbox(
                    label="Model ID", value="openai/gpt-oss-120b", scale=2,
                )
            with gr.Row():
                dev_diagnose_btn = gr.Button("Diagnose Only", variant="secondary", scale=1)
                dev_full_btn = gr.Button("Full Cycle", variant="primary", scale=1)
                dev_status_btn = gr.Button("Status", variant="secondary", scale=1)
            dev_output = gr.Textbox(
                label="Super Supervisor Output",
                interactive=False, lines=15,
            )

        gr.Markdown("---")

        with gr.Row():
            clear_btn   = gr.Button("Clear", scale=1)
            restart_btn = gr.Button("Restart", scale=1)

    gr.Markdown(
        "© MOBIUS LLC · Created by Taiko Toeda",
        elem_classes=["mobius-footer"],
    )

    # ── Events ───────────────────────────────────────────────────────

    proc_inputs  = [query_box, chatbot, session_state, mobius_state, explore_state, tz_dropdown]
    proc_outputs = [chatbot, session_state, query_box, trace_out, right_summary, right_detail]

    def _update_turn_selector(session_data):
        th = (session_data or {}).get("trace_history", [])
        if not th:
            return gr.update(choices=[], value=None)
        choices = [(f"Turn {t['turn']}: {t['query']}", t['turn']) for t in th]
        return gr.update(choices=choices, value=th[-1]["turn"])

    def _show_selected_turn(selected_turn, session_data):
        th = (session_data or {}).get("trace_history", [])
        if not selected_turn or not th:
            return ""
        entry = next((t for t in th if t["turn"] == selected_turn), None)
        return entry["detail"] if entry else ""

    send_btn.click(process_stream, proc_inputs, proc_outputs).then(
        _update_turn_selector, session_state, turn_selector,
    )
    query_box.submit(process_stream, proc_inputs, proc_outputs).then(
        _update_turn_selector, session_state, turn_selector,
    )
    turn_selector.change(
        _show_selected_turn, [turn_selector, session_state], right_detail,
    )

    # MOBIUS toggle
    def _mobius_on(explore_on):
        return (
            True,
            gr.update(variant="primary"),
            gr.update(variant="secondary"),
            get_mode_status(True, explore_on),
        )

    def _mobius_off(explore_on):
        return (
            False,
            gr.update(variant="secondary"),
            gr.update(variant="primary"),
            get_mode_status(False, explore_on),
        )

    mobius_on_btn.click(
        _mobius_on, explore_state,
        [mobius_state, mobius_on_btn, mobius_off_btn, mode_display]
    )
    mobius_off_btn.click(
        _mobius_off, explore_state,
        [mobius_state, mobius_on_btn, mobius_off_btn, mode_display]
    )

    # Explore toggle
    def _explore_on(mobius_on):
        return (
            True,
            gr.update(variant="primary"),
            gr.update(variant="secondary"),
            get_mode_status(mobius_on, True),
        )

    def _explore_off(mobius_on):
        return (
            False,
            gr.update(variant="secondary"),
            gr.update(variant="primary"),
            get_mode_status(mobius_on, False),
        )

    explore_on_btn.click(
        _explore_on, mobius_state,
        [explore_state, explore_on_btn, explore_off_btn, mode_display]
    )
    explore_off_btn.click(
        _explore_off, mobius_state,
        [explore_state, explore_on_btn, explore_off_btn, mode_display]
    )

    # Copy conversation: server builds text → export_out → JS copies from it
    copy_btn.click(
        lambda hist, sd: (*do_copy_conversation(hist, sd), "txt"),
        [chatbot, session_state], [export_out, copy_feedback, export_ext],
    ).then(
        None, None, None, js=COPY_JS,
    ).then(
        lambda: "", None, copy_feedback, js=COPY_RESET_JS,
    )

    # Export (preview in text area + set extension for download)
    md_btn.click(
        lambda hist, sd: (do_export_md(hist, sd), "md"),
        [chatbot, session_state], [export_out, export_ext],
    )
    json_btn.click(
        lambda hist, sd: (do_export_json(hist, sd), "json"),
        [chatbot, session_state], [export_out, export_ext],
    )

    # Download: write export_out content to temp file → gr.File
    def _do_download(text, ext):
        import tempfile
        if not text or not text.strip():
            return gr.update(value=None)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"mobius_{ts}.{ext}"
        path = os.path.join(tempfile.gettempdir(), fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return gr.update(value=path)

    export_dl_btn.click(
        _do_download, [export_out, export_ext], export_file,
    )

    # Upload / Toggle / Delete (Box A)
    upload_file.change(
        _handle_upload,
        upload_file, [upload_status, doc_list, box_a_selector],
    )
    box_a_toggle_btn.click(
        _handle_toggle,
        box_a_selector, [upload_status, doc_list, box_a_selector],
    )
    box_a_delete_btn.click(
        _handle_delete,
        box_a_selector, [upload_status, doc_list, box_a_selector],
    )

    # Clear
    clear_btn.click(clear_all, None,
                    [chatbot, session_state, export_out, trace_out, right_summary, right_detail])

    # Restart
    def _restart():
        import threading
        def _do():
            import time; time.sleep(0.5)
            os.execv(sys.executable, [sys.executable] + sys.argv)
        threading.Thread(target=_do, daemon=True).start()

    restart_btn.click(
        _restart, None, None,
        js="() => { setTimeout(() => location.reload(), 1500); }"
    )

    # ── Developer Mode (Super Supervisor) ─────────────────────────
    dev_mode_toggle.change(
        lambda on: gr.update(visible=on),
        dev_mode_toggle, dev_panel,
    )

    def _run_supervisor(mode, api_key, model_id):
        import subprocess as _sp
        env = os.environ.copy()
        if api_key:
            env["GROQ_API_KEY"] = api_key
        cmd = [sys.executable, "scripts/supervisor.py"]
        if mode == "diagnose":
            cmd.append("--diagnose")
        elif mode == "status":
            cmd.append("--status")
        try:
            result = _sp.run(
                cmd, capture_output=True, text=True,
                timeout=600, env=env, cwd=ROOT,
            )
            output = result.stdout
            if result.stderr:
                output += "\n--- stderr ---\n" + result.stderr
            return output or "(no output)"
        except _sp.TimeoutExpired:
            return "Timeout: execution exceeded 600 seconds"
        except Exception as e:
            return f"Error: {e}"

    dev_diagnose_btn.click(
        lambda key, mid: _run_supervisor("diagnose", key, mid),
        [dev_api_key, dev_model_id], dev_output,
    )
    dev_full_btn.click(
        lambda key, mid: _run_supervisor("full", key, mid),
        [dev_api_key, dev_model_id], dev_output,
    )
    dev_status_btn.click(
        lambda key, mid: _run_supervisor("status", key, mid),
        [dev_api_key, dev_model_id], dev_output,
    )

    # ── Box M Save Session Memory ──────────────────────────────────
    def _save_session_memory():
        try:
            from scripts.boxm_export import export_capsules
            path = export_capsules(min_salience=0.3)
            if path:
                return f"Saved to {path}"
            return "No capsules to export (empty session or below salience threshold)."
        except Exception as e:
            return f"Export error: {e}"

    boxm_save_btn.click(_save_session_memory, None, boxm_status)

    # ── Phase G.5 / G.6 / G.7: wire carryover controls ──────────────────
    def _carryover_view(session):
        """Compute the canonical UI view for the current session:
        (chip_label, help_text, save_btn_update).

        Uses `presentation_status()` as the single source of truth; never
        exposes raw Box P internals; never dumps candidate JSON."""
        try:
            from src.memory.carryover import presentation_status
        except Exception:
            return "Not ready", "Nothing to carry forward yet.", gr.update(interactive=False)
        p = presentation_status(session)
        btn = gr.update(interactive=bool(p.can_save))
        return p.label, p.help_text, btn

    def _on_carryover_toggle(opt_out_on: bool, session_data):
        """Toggle carryover for the active session. opt_out_on=True means
        the user selected "do not carry forward"; we call disable_carryover.
        Active-session Box M is NOT touched. Also refreshes the
        continuity chip + help text, and disables the save button if
        the candidate is no longer promotable."""
        session_data = session_data or {}
        session = session_data.get("session")
        if session is None:
            session = SessionState()
            session_data = dict(session_data)
            session_data["session"] = session
        try:
            session.set_carryover(allowed=(not bool(opt_out_on)))
        except Exception:
            pass
        carryover_chip = ("Off for this conversation"
                          if bool(opt_out_on) else "On")
        chip, help_text, btn = _carryover_view(session)
        return session_data, carryover_chip, chip, help_text, btn

    carryover_opt_out_toggle.change(
        _on_carryover_toggle,
        inputs=[carryover_opt_out_toggle, session_state],
        outputs=[
            session_state, carryover_status_chip,
            carryover_pending_chip, carryover_help_md, carryover_save_btn,
        ],
    )

    def _on_carryover_save(session_data):
        """Phase G.6 / G.7: manual 'Save continuity now' action. Reuses
        the same evaluation path as the automatic trigger; promotes the
        candidate only when it is promotable AND opt-out is off. Never
        dumps raw transcript into Box P (promotion funnels through
        `distill_from_user_map`).

        When the candidate is not promotable (button ideally disabled,
        but a double-click or programmatic trigger might still land
        here), this is a safe no-op that updates the chip/help_text
        honestly rather than silently swallowing."""
        session_data = session_data or {}
        session = session_data.get("session")
        if session is None:
            session = SessionState()
            session_data = dict(session_data)
            session_data["session"] = session
        try:
            from src.memory.carryover import (
                trigger_manual_checkpoint, presentation_status,
            )
            p = presentation_status(session)
            if p.can_save:
                profile = session.ensure_box_p()
                trigger_manual_checkpoint(
                    session, promote=True, profile=profile,
                    language=getattr(session, "active_language", None),
                )
        except Exception:
            pass
        chip, help_text, btn = _carryover_view(session)
        return session_data, chip, help_text, btn

    carryover_save_btn.click(
        _on_carryover_save,
        inputs=[session_state],
        outputs=[
            session_state, carryover_pending_chip,
            carryover_help_md, carryover_save_btn,
        ],
    )

    # ── Phase G.11: profile selector + Box B / C uploads ──────────────
    def _on_profile_change(profile_id, session_data):
        """Change the active authority + retrieval profile for the
        session via the canonical G.3 helper."""
        session_data = session_data or {}
        session = session_data.get("session")
        if session is None:
            session = SessionState()
            session_data = dict(session_data)
            session_data["session"] = session
        try:
            session.apply_profile_selection(profile_id, profile_id)
        except Exception:
            pass
        active = getattr(session, "selected_authority_profile_id", "") or "balanced_default"
        return session_data, active

    profile_dropdown.change(
        _on_profile_change,
        inputs=[profile_dropdown, session_state],
        outputs=[session_state, profile_status],
    )

    def _on_box_b_upload(file_obj):
        if _box_b_mgr is None or file_obj is None:
            return "(Box B not available)", ""
        try:
            path = getattr(file_obj, "name", None) or file_obj
            fname = os.path.basename(path)
            info = _box_b_mgr.add_document(path, fname)
            docs = _box_b_mgr.list_documents()
            status = f"Added {fname}: {info.get('chunk_count', 0)} chunks"
            listing = "\n".join(f"- {d['filename']} ({d['status']})" for d in docs) or "(empty)"
            return listing, status
        except Exception as e:
            return f"(Box B error: {e})", ""

    if _box_b_mgr is not None:
        box_b_upload.upload(
            _on_box_b_upload,
            inputs=[box_b_upload],
            outputs=[box_b_doc_list, box_b_status],
        )

    def _on_box_c_upload(file_obj):
        if _box_c_mgr is None or file_obj is None:
            return "(Box C not available)", ""
        try:
            path = getattr(file_obj, "name", None) or file_obj
            fname = os.path.basename(path)
            info = _box_c_mgr.add_document(path, fname)
            docs = _box_c_mgr.list_documents()
            status = f"Added {fname}: {info.get('chunk_count', 0)} chunks"
            listing = "\n".join(f"- {d['filename']} ({d['status']})" for d in docs) or "(empty)"
            return listing, status
        except Exception as e:
            return f"(Box C error: {e})", ""

    if _box_c_mgr is not None:
        box_c_upload.upload(
            _on_box_c_upload,
            inputs=[box_c_upload],
            outputs=[box_c_doc_list, box_c_status],
        )

    # ── Box M Load Session Memory ──────────────────────────────────
    def _list_snapshots():
        import glob as _glob
        snap_dir = os.path.join(ROOT, "data", "boxm_snapshots")
        files = sorted(_glob.glob(os.path.join(snap_dir, "session_*.json")), reverse=True)
        if not files:
            return gr.update(visible=False), "No snapshots found."
        choices = []
        for f in files[:10]:
            try:
                with open(f) as fp:
                    data = json.load(fp)
                count = data.get("capsule_count", 0)
                date = data.get("exported_at", "unknown")[:19]
                label = f"{os.path.basename(f)} ({count} capsules, {date})"
            except Exception:
                label = os.path.basename(f)
            choices.append((label, f))
        return gr.update(choices=choices, visible=True), f"Found {len(choices)} snapshots."

    def _do_import(selected_file):
        if not selected_file:
            return "No snapshot selected."
        try:
            from scripts.boxm_import import import_capsules
            n = import_capsules(selected_file, auto_confirm=True)
            if n < 0:
                return "Import failed (file not found)."
            return f"Imported {n} capsules."
        except Exception as e:
            return f"Import error: {e}"

    boxm_load_btn.click(
        _list_snapshots, None, [boxm_load_row, boxm_status],
    )
    boxm_import_btn.click(
        _do_import, boxm_snapshot_dd, boxm_status,
    )


# ── Startup: check for previous snapshots ────────────────────────
def _check_previous_snapshots():
    import glob as _glob
    snapshot_dir = os.path.join(ROOT, "data", "boxm_snapshots")
    if os.path.exists(snapshot_dir):
        snapshots = sorted(_glob.glob(os.path.join(snapshot_dir, "session_*.json")))
        if snapshots:
            latest = snapshots[-1]
            print(f"[Box M] Previous session snapshot found: {os.path.basename(latest)}")
            print(f"[Box M] To import: python scripts/boxm_import.py --latest")

_check_previous_snapshots()


def _on_shutdown():
    """Phase G.5: retired blocking end-of-session save modal.

    The prior implementation issued a blocking y/n prompt on process
    exit — an awkward "do you want to save this conversation" modal.
    Carryover is now controlled by the in-UI toggle
    ("Do not carry this conversation forward") and by natural
    checkpoint-based promotion into Box P. Shutdown is silent by design.
    """
    try:
        from src.kernel import routing_engine as _re
        if not getattr(_re, "_MEMORY_AVAILABLE", False):
            return
        indexer = _re._memory_indexer
        if indexer is None:
            return
        count = indexer.count()
        if count:
            # Informational only — no prompt, no blocking stdin read.
            print(f"[Box M] {count} capsules in session memory (shutdown, silent).")
    except Exception:   # noqa: BLE001
        pass

atexit.register(_on_shutdown)


if __name__ == "__main__":
    print("[UI] Starting MOBIUS MMV UI on http://localhost:7860")
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True,
        theme=gr.themes.Soft(),
    )
