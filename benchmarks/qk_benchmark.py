#!/usr/bin/env python3
"""
QK Effectiveness Benchmark
50 queries x 4 conditions x 3 models = 600 inferences
Groq runs in parallel with Ollama for time efficiency.

Author : Taiko Toeda / MOBIUS LLC
"""
import json, os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from src.adapters.question_kernel import (
    ALL_QK, select_kernels, format_kernel_block, get_zone_for_intent
)

# ── Queries ──────────────────────────────────────────────────────────────────

QUERIES = [
    {"id":"F01","q":"What is the boiling point of water at sea level?","intent":"factual_query","category":"factual","ground_truth":"100 degrees Celsius or 212 degrees Fahrenheit"},
    {"id":"F02","q":"How many chromosomes do humans have?","intent":"factual_query","category":"factual","ground_truth":"46 chromosomes (23 pairs)"},
    {"id":"F03","q":"What is the speed of light in vacuum?","intent":"factual_query","category":"factual","ground_truth":"approximately 299,792,458 meters per second"},
    {"id":"F04","q":"What is the chemical formula for table salt?","intent":"factual_query","category":"factual","ground_truth":"NaCl (sodium chloride)"},
    {"id":"F05","q":"How many planets are in our solar system?","intent":"factual_query","category":"factual","ground_truth":"8 planets"},
    {"id":"F06","q":"What is the atomic number of carbon?","intent":"factual_query","category":"factual","ground_truth":"6"},
    {"id":"F07","q":"In what year did World War II end?","intent":"factual_query","category":"factual","ground_truth":"1945"},
    {"id":"F08","q":"What is the largest ocean on Earth?","intent":"factual_query","category":"factual","ground_truth":"Pacific Ocean"},
    {"id":"F09","q":"What is the square root of 144?","intent":"factual_query","category":"factual","ground_truth":"12"},
    {"id":"F10","q":"What is the capital of Australia?","intent":"factual_query","category":"factual","ground_truth":"Canberra"},
    {"id":"F11","q":"How many bones are in the adult human body?","intent":"factual_query","category":"factual","ground_truth":"206"},
    {"id":"F12","q":"What element does the symbol Fe represent?","intent":"factual_query","category":"factual","ground_truth":"Iron"},
    {"id":"U01","q":"How much does it cost?","intent":"clarification","category":"underspec","ground_truth":"SHOULD_ASK_CLARIFICATION"},
    {"id":"U02","q":"Is it safe?","intent":"clarification","category":"underspec","ground_truth":"SHOULD_ASK_CLARIFICATION"},
    {"id":"U03","q":"What's the best one?","intent":"clarification","category":"underspec","ground_truth":"SHOULD_ASK_CLARIFICATION"},
    {"id":"U04","q":"Can you fix it?","intent":"clarification","category":"underspec","ground_truth":"SHOULD_ASK_CLARIFICATION"},
    {"id":"U05","q":"When does it start?","intent":"clarification","category":"underspec","ground_truth":"SHOULD_ASK_CLARIFICATION"},
    {"id":"U06","q":"What happened to the company?","intent":"clarification","category":"underspec","ground_truth":"SHOULD_ASK_CLARIFICATION"},
    {"id":"U07","q":"Should I take it?","intent":"clarification","category":"underspec","ground_truth":"SHOULD_ASK_CLARIFICATION"},
    {"id":"U08","q":"Is the treatment effective?","intent":"clarification","category":"underspec","ground_truth":"SHOULD_ASK_CLARIFICATION"},
    {"id":"U09","q":"What size should I get?","intent":"clarification","category":"underspec","ground_truth":"SHOULD_ASK_CLARIFICATION"},
    {"id":"U10","q":"Where should I go?","intent":"clarification","category":"underspec","ground_truth":"SHOULD_ASK_CLARIFICATION"},
    {"id":"E01","q":"How many moons does Mars have and what are their diameters?","intent":"factual_query","category":"epistemic","ground_truth":"2 moons: Phobos (~22km) and Deimos (~12km)"},
    {"id":"E02","q":"Who wrote the novel 'The Great Gatsby' and in what year was it published?","intent":"factual_query","category":"epistemic","ground_truth":"F. Scott Fitzgerald, published 1925"},
    {"id":"E03","q":"What is the half-life of Carbon-14?","intent":"factual_query","category":"epistemic","ground_truth":"approximately 5,730 years"},
    {"id":"E04","q":"Name the four chambers of the human heart.","intent":"factual_query","category":"epistemic","ground_truth":"right atrium, right ventricle, left atrium, left ventricle"},
    {"id":"E05","q":"What is the Pythagorean theorem and who is it attributed to?","intent":"factual_query","category":"epistemic","ground_truth":"a² + b² = c², attributed to Pythagoras"},
    {"id":"E06","q":"What are the three laws of thermodynamics?","intent":"factual_query","category":"epistemic","ground_truth":"energy conservation, entropy increase, absolute zero unreachable"},
    {"id":"E07","q":"How many symphonies did Beethoven compose?","intent":"factual_query","category":"epistemic","ground_truth":"9 symphonies"},
    {"id":"E08","q":"What is the distance from Earth to the Sun?","intent":"factual_query","category":"epistemic","ground_truth":"approximately 150 million km or 93 million miles or 1 AU"},
    {"id":"E09","q":"Name all noble gases.","intent":"factual_query","category":"epistemic","ground_truth":"helium, neon, argon, krypton, xenon, radon"},
    {"id":"E10","q":"What treaty established the European Economic Community and when?","intent":"factual_query","category":"epistemic","ground_truth":"Treaty of Rome, 1957"},
    {"id":"O01","q":"What programming language should I learn first?","intent":"instruction_request","category":"opinion","ground_truth":"SHOULD_PRESENT_OPTIONS_NOT_ASSERT"},
    {"id":"O02","q":"Is it better to rent or buy a house?","intent":"instruction_request","category":"opinion","ground_truth":"SHOULD_PRESENT_TRADEOFFS"},
    {"id":"O03","q":"What's the healthiest diet?","intent":"instruction_request","category":"opinion","ground_truth":"SHOULD_NOTE_UNCERTAINTY"},
    {"id":"O04","q":"Should I invest in stocks or bonds?","intent":"instruction_request","category":"opinion","ground_truth":"SHOULD_NOTE_PERSONAL_CIRCUMSTANCES"},
    {"id":"O05","q":"Is AI going to replace all jobs?","intent":"instruction_request","category":"opinion","ground_truth":"SHOULD_PRESENT_NUANCED_VIEW"},
    {"id":"O06","q":"What is the meaning of life?","intent":"instruction_request","category":"opinion","ground_truth":"SHOULD_PRESENT_PERSPECTIVES"},
    {"id":"O07","q":"Is nuclear energy safe?","intent":"instruction_request","category":"opinion","ground_truth":"SHOULD_PRESENT_TRADEOFFS"},
    {"id":"O08","q":"Which is better, Mac or Windows?","intent":"instruction_request","category":"opinion","ground_truth":"SHOULD_PRESENT_OPTIONS_NOT_ASSERT"},
    {"id":"C01","q":"Hello!","intent":"casual_greeting","category":"casual","ground_truth":"GREETING_RESPONSE"},
    {"id":"C02","q":"How are you today?","intent":"casual_greeting","category":"casual","ground_truth":"GREETING_RESPONSE"},
    {"id":"C03","q":"Tell me a fun fact.","intent":"creative_request","category":"casual","ground_truth":"ANY_INTERESTING_FACT"},
    {"id":"C04","q":"What's a good joke?","intent":"creative_request","category":"casual","ground_truth":"HUMOR_ATTEMPT"},
    {"id":"C05","q":"Good morning!","intent":"casual_greeting","category":"casual","ground_truth":"GREETING_RESPONSE"},
    {"id":"C06","q":"Write a haiku about rain.","intent":"creative_request","category":"casual","ground_truth":"HAIKU_5_7_5"},
    {"id":"C07","q":"Thank you for your help!","intent":"casual_greeting","category":"casual","ground_truth":"ACKNOWLEDGMENT"},
    {"id":"C08","q":"What's your favorite color?","intent":"casual_greeting","category":"casual","ground_truth":"ANY_RESPONSE"},
    {"id":"C09","q":"Can you sing?","intent":"creative_request","category":"casual","ground_truth":"ANY_CREATIVE_RESPONSE"},
    {"id":"C10","q":"Goodbye!","intent":"casual_greeting","category":"casual","ground_truth":"FAREWELL_RESPONSE"},
]

# ── API calls ────────────────────────────────────────────────────────────────

_print_lock = threading.Lock()

def _log(msg):
    with _print_lock:
        print(msg, flush=True)

def load_groq_key():
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    for p in [Path(".env"), Path.home() / ".env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("GROQ_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"\'')
    raise RuntimeError("GROQ_API_KEY not found")

def call_ollama(prompt, model, endpoint="http://localhost:11434", max_tokens=512, timeout=120):
    t0 = time.time()
    try:
        r = requests.post(f"{endpoint}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "think": False, "options": {"temperature": 0.2, "num_predict": max_tokens}},
            timeout=timeout)
        r.raise_for_status()
        return {"text": r.json().get("response", ""), "latency_ms": int((time.time()-t0)*1000), "error": None}
    except Exception as e:
        return {"text": "", "latency_ms": int((time.time()-t0)*1000), "error": str(e)}

def call_groq(prompt, model="openai/gpt-oss-20b", api_key=None, max_tokens=512):
    t0 = time.time()
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.2, "max_tokens": max_tokens},
            timeout=60)
        r.raise_for_status()
        return {"text": r.json()["choices"][0]["message"]["content"],
                "latency_ms": int((time.time()-t0)*1000), "error": None}
    except Exception as e:
        return {"text": "", "latency_ms": int((time.time()-t0)*1000), "error": str(e)}

# ── Prompt builders ──────────────────────────────────────────────────────────

def build_no_qk(query):
    return f"User: {query}\n\nRespond concisely and accurately."

def build_fixed_qk(query):
    block = format_kernel_block(ALL_QK)
    return f"{block}\n\nUser: {query}\n\nRespond concisely and accurately."

def build_ism_qk(query, intent):
    zone = get_zone_for_intent(intent)
    kernels = select_kernels(intent, zone=zone, route="answer")
    block = format_kernel_block(kernels)
    base = f"User: {query}\n\nRespond concisely and accurately."
    return f"{block}\n\n{base}" if block else base

def build_pass2(draft, query):
    return f"Original query: {query}\n\nDraft response:\n{draft}\n\nRefine this response for accuracy and clarity."

# ── Per-model runner ─────────────────────────────────────────────────────────

CONDITIONS = ["baseline", "fixed_qk", "ism_adaptive", "full_pipeline"]

def run_model(model_cfg, queries, label_prefix=""):
    results = []
    total = len(queries) * len(CONDITIONS)
    count = 0
    for cond in CONDITIONS:
        for q in queries:
            count += 1
            qid, query, intent = q["id"], q["q"], q["intent"]

            if cond == "baseline":
                prompt = build_no_qk(query)
            elif cond == "fixed_qk":
                prompt = build_fixed_qk(query)
            else:  # ism_adaptive or full_pipeline
                prompt = build_ism_qk(query, intent)

            # Pass 1
            if model_cfg["backend"] == "ollama":
                r1 = call_ollama(prompt, model_cfg["model_id"], model_cfg["endpoint"])
            else:
                r1 = call_groq(prompt, model_cfg["model_id"], model_cfg.get("api_key"))
                time.sleep(0.5)

            p1_text, p1_lat = r1["text"], r1["latency_ms"]
            p2_text, p2_lat = "", 0

            # Pass 2 (full_pipeline only)
            if cond == "full_pipeline" and not r1["error"]:
                p2_prompt = build_pass2(p1_text, query)
                ep2 = model_cfg.get("endpoint2") or model_cfg.get("endpoint", "")
                if model_cfg["backend"] == "ollama":
                    r2 = call_ollama(p2_prompt, model_cfg["model_id"], ep2, max_tokens=256)
                else:
                    r2 = call_groq(p2_prompt, model_cfg["model_id"], model_cfg.get("api_key"), max_tokens=256)
                    time.sleep(0.5)
                p2_text, p2_lat = r2["text"], r2["latency_ms"]

            final = p2_text if p2_text else p1_text
            _log(f"  [{label_prefix}{count}/{total}] {model_cfg['name']}/{cond}/{qid} ({p1_lat+p2_lat}ms) {'ERR' if r1.get('error') else 'OK'}")

            results.append({
                "query_id": qid, "query": query, "category": q["category"],
                "intent": intent, "ground_truth": q["ground_truth"],
                "model": model_cfg["name"], "condition": cond,
                "response": final, "pass1_text": p1_text, "pass2_text": p2_text,
                "pass1_latency_ms": p1_lat, "pass2_latency_ms": p2_lat,
                "total_latency_ms": p1_lat + p2_lat, "error": r1.get("error"),
            })
    return results

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    groq_key = load_groq_key()
    print(f"GROQ_API_KEY: {groq_key[:8]}...")

    # Verify
    for port, model in [(11434, "phi4-mini:latest"), (11435, "qwen3.5:9b")]:
        r = call_ollama("ping", model, f"http://localhost:{port}", max_tokens=4)
        print(f"  Port {port} ({model}): {'OK' if not r['error'] else 'FAIL: '+str(r['error'])}")
    r = call_groq("ping", api_key=groq_key, max_tokens=4)
    print(f"  Groq: {'OK' if not r['error'] else 'FAIL: '+str(r['error'])}")

    models_ollama = [
        {"name": "phi4-mini", "backend": "ollama", "model_id": "phi4-mini:latest",
         "endpoint": "http://localhost:11434", "endpoint2": "http://localhost:11435"},
        {"name": "qwen3.5-9b", "backend": "ollama", "model_id": "qwen3.5:9b",
         "endpoint": "http://localhost:11434", "endpoint2": "http://localhost:11435"},
    ]
    model_groq = {"name": "gpt-oss-20b", "backend": "groq",
                  "model_id": "openai/gpt-oss-20b", "api_key": groq_key}

    print(f"\n=== Benchmark: {len(QUERIES)} queries x {len(CONDITIONS)} conditions x 3 models = {len(QUERIES)*len(CONDITIONS)*3} ===\n")
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_groq = ex.submit(run_model, model_groq, QUERIES, "G:")
        f_ollama = ex.submit(
            lambda: run_model(models_ollama[0], QUERIES, "O1:") + run_model(models_ollama[1], QUERIES, "O2:"),
        )
        all_results = []
        for f in as_completed([f_groq, f_ollama]):
            all_results.extend(f.result())

    elapsed = time.time() - t0
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"qk_benchmark_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n=== Done in {elapsed:.0f}s ===")
    print(f"Results: {len(all_results)} inferences → {out_file}")

if __name__ == "__main__":
    main()
