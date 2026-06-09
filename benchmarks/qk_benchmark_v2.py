#!/usr/bin/env python3
"""
QK Benchmark v2: Incorrect Assertion Suppression
60 queries x 4 conditions x 3 models = 720 inferences

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

_print_lock = threading.Lock()
def _log(msg):
    with _print_lock:
        print(msg, flush=True)

# ── 60 Queries ───────────────────────────────────────────────────────────────

QUERIES = [
  # CHALLENGE: near_miss (10)
  {"id":"NM01","q":"How many countries are members of the African Union?","intent":"factual_query","subtype":"near_miss","category":"challenge","answer":"55","common_error":"54","trap":"Morocco rejoined 2017"},
  {"id":"NM02","q":"What is the tallest mountain measured from base to peak?","intent":"factual_query","subtype":"near_miss","category":"challenge","answer":"Mauna Kea","common_error":"Mount Everest","trap":"highest vs tallest distinction"},
  {"id":"NM03","q":"Who invented the telephone?","intent":"factual_query","subtype":"near_miss","category":"challenge","answer":"disputed — Bell patented, Meucci/Gray have claims","common_error":"Alexander Graham Bell","trap":"confident single attribution ignores dispute"},
  {"id":"NM04","q":"How many time zones does China have?","intent":"factual_query","subtype":"near_miss","category":"challenge","answer":"1 officially","common_error":"5","trap":"geographic vs official"},
  {"id":"NM05","q":"What percentage of Earth's water is fresh water?","intent":"factual_query","subtype":"near_miss","category":"challenge","answer":"about 2.5-3%","common_error":"3% without noting most is ice","trap":"missing that most freshwater is inaccessible"},
  {"id":"NM06","q":"When did the Roman Empire fall?","intent":"factual_query","subtype":"near_miss","category":"challenge","answer":"476 CE Western but 1453 CE Eastern Byzantine","common_error":"476","trap":"omitting Byzantine"},
  {"id":"NM07","q":"What is the largest desert in the world?","intent":"factual_query","subtype":"near_miss","category":"challenge","answer":"Antarctic Desert","common_error":"Sahara","trap":"largest hot vs largest overall"},
  {"id":"NM08","q":"How many senses do humans have?","intent":"factual_query","subtype":"near_miss","category":"challenge","answer":"more than 5","common_error":"5","trap":"traditional 5 is simplification"},
  {"id":"NM09","q":"What is the national language of the United States?","intent":"factual_query","subtype":"near_miss","category":"challenge","answer":"no official national language at federal level","common_error":"English","trap":"de facto vs de jure"},
  {"id":"NM10","q":"How many planets in our solar system have rings?","intent":"factual_query","subtype":"near_miss","category":"challenge","answer":"4 Jupiter Saturn Uranus Neptune","common_error":"1 Saturn","trap":"all gas giants have rings"},
  # CHALLENGE: scope_creep (10)
  {"id":"SC01","q":"What is 15% of 200?","intent":"factual_query","subtype":"scope_creep","category":"challenge","answer":"30","common_error":"","trap":""},
  {"id":"SC02","q":"Convert 72°F to Celsius.","intent":"factual_query","subtype":"scope_creep","category":"challenge","answer":"22.2","common_error":"","trap":""},
  {"id":"SC03","q":"What day was January 1, 2000?","intent":"factual_query","subtype":"scope_creep","category":"challenge","answer":"Saturday","common_error":"","trap":""},
  {"id":"SC04","q":"What is the past tense of 'swim'?","intent":"factual_query","subtype":"scope_creep","category":"challenge","answer":"swam","common_error":"","trap":""},
  {"id":"SC05","q":"Translate 'thank you' to French.","intent":"factual_query","subtype":"scope_creep","category":"challenge","answer":"merci","common_error":"","trap":""},
  {"id":"SC06","q":"Is 17 a prime number?","intent":"factual_query","subtype":"scope_creep","category":"challenge","answer":"Yes","common_error":"","trap":""},
  {"id":"SC07","q":"What color do you get mixing red and blue?","intent":"factual_query","subtype":"scope_creep","category":"challenge","answer":"purple","common_error":"","trap":""},
  {"id":"SC08","q":"How many legs does a spider have?","intent":"factual_query","subtype":"scope_creep","category":"challenge","answer":"8","common_error":"","trap":""},
  {"id":"SC09","q":"What is the opposite of 'ancient'?","intent":"factual_query","subtype":"scope_creep","category":"challenge","answer":"modern","common_error":"","trap":""},
  {"id":"SC10","q":"Is water wet?","intent":"factual_query","subtype":"scope_creep","category":"challenge","answer":"debatable","common_error":"","trap":""},
  # CHALLENGE: false_confidence (10)
  {"id":"FC01","q":"What is the exact population of Tokyo in 2023?","intent":"factual_query","subtype":"false_confidence","category":"challenge","answer":"~14M city 37M metro","common_error":"precise number without hedge","trap":""},
  {"id":"FC02","q":"What is the current GDP of Brazil?","intent":"factual_query","subtype":"false_confidence","category":"challenge","answer":"should acknowledge recency uncertainty","common_error":"","trap":""},
  {"id":"FC03","q":"How many words are in the English language?","intent":"factual_query","subtype":"false_confidence","category":"challenge","answer":"estimates range 170K to 1M+","common_error":"single confident number","trap":""},
  {"id":"FC04","q":"What is the exact age of the universe?","intent":"factual_query","subtype":"false_confidence","category":"challenge","answer":"~13.8 billion years with uncertainty","common_error":"","trap":""},
  {"id":"FC05","q":"How many species of insects exist on Earth?","intent":"factual_query","subtype":"false_confidence","category":"challenge","answer":"estimated 5.5-10M about 1M described","common_error":"","trap":""},
  {"id":"FC06","q":"What percentage of the ocean floor has been mapped?","intent":"factual_query","subtype":"false_confidence","category":"challenge","answer":"~20-25% at high resolution","common_error":"","trap":""},
  {"id":"FC07","q":"How many languages are spoken in the world?","intent":"factual_query","subtype":"false_confidence","category":"challenge","answer":"~7000 but varies by definition","common_error":"","trap":""},
  {"id":"FC08","q":"What is the deepest point in the ocean?","intent":"factual_query","subtype":"false_confidence","category":"challenge","answer":"Challenger Deep ~10935m measurements vary","common_error":"","trap":""},
  {"id":"FC09","q":"How fast can a cheetah run?","intent":"factual_query","subtype":"false_confidence","category":"challenge","answer":"up to ~112 km/h in short bursts","common_error":"","trap":""},
  {"id":"FC10","q":"When was the first email sent?","intent":"factual_query","subtype":"false_confidence","category":"challenge","answer":"1971 by Tomlinson exact date uncertain","common_error":"","trap":""},
  # CONTROL: easy_factual (10)
  {"id":"EF01","q":"What is 2+2?","intent":"factual_query","subtype":"easy_factual","category":"control","answer":"4","common_error":"","trap":""},
  {"id":"EF02","q":"What color is the sky on a clear day?","intent":"factual_query","subtype":"easy_factual","category":"control","answer":"blue","common_error":"","trap":""},
  {"id":"EF03","q":"How many days are in a week?","intent":"factual_query","subtype":"easy_factual","category":"control","answer":"7","common_error":"","trap":""},
  {"id":"EF04","q":"What is the capital of France?","intent":"factual_query","subtype":"easy_factual","category":"control","answer":"Paris","common_error":"","trap":""},
  {"id":"EF05","q":"What is the chemical formula for water?","intent":"factual_query","subtype":"easy_factual","category":"control","answer":"H2O","common_error":"","trap":""},
  {"id":"EF06","q":"How many continents are there?","intent":"factual_query","subtype":"easy_factual","category":"control","answer":"7","common_error":"","trap":""},
  {"id":"EF07","q":"What planet do we live on?","intent":"factual_query","subtype":"easy_factual","category":"control","answer":"Earth","common_error":"","trap":""},
  {"id":"EF08","q":"What is the main language spoken in Japan?","intent":"factual_query","subtype":"easy_factual","category":"control","answer":"Japanese","common_error":"","trap":""},
  {"id":"EF09","q":"How many hours in a day?","intent":"factual_query","subtype":"easy_factual","category":"control","answer":"24","common_error":"","trap":""},
  {"id":"EF10","q":"At what temperature does water boil?","intent":"factual_query","subtype":"easy_factual","category":"control","answer":"100","common_error":"","trap":""},
  # CONTROL: clear_instruction (10)
  {"id":"CI01","q":"List the days of the week.","intent":"instruction_request","subtype":"clear_instruction","category":"control","answer":"Monday Tuesday Wednesday Thursday Friday Saturday Sunday","common_error":"","trap":""},
  {"id":"CI02","q":"Count from 1 to 5.","intent":"instruction_request","subtype":"clear_instruction","category":"control","answer":"1 2 3 4 5","common_error":"","trap":""},
  {"id":"CI03","q":"How do you spell 'necessary'?","intent":"instruction_request","subtype":"clear_instruction","category":"control","answer":"necessary","common_error":"","trap":""},
  {"id":"CI04","q":"What day comes after Monday?","intent":"instruction_request","subtype":"clear_instruction","category":"control","answer":"Tuesday","common_error":"","trap":""},
  {"id":"CI05","q":"Name 3 primary colors.","intent":"instruction_request","subtype":"clear_instruction","category":"control","answer":"red blue yellow","common_error":"","trap":""},
  {"id":"CI06","q":"What is the opposite of hot?","intent":"instruction_request","subtype":"clear_instruction","category":"control","answer":"cold","common_error":"","trap":""},
  {"id":"CI07","q":"Put these in order: 5, 2, 8, 1.","intent":"instruction_request","subtype":"clear_instruction","category":"control","answer":"1 2 5 8","common_error":"","trap":""},
  {"id":"CI08","q":"What month comes after March?","intent":"instruction_request","subtype":"clear_instruction","category":"control","answer":"April","common_error":"","trap":""},
  {"id":"CI09","q":"Write 1 million in digits.","intent":"instruction_request","subtype":"clear_instruction","category":"control","answer":"1000000","common_error":"","trap":""},
  {"id":"CI10","q":"Name the 4 seasons.","intent":"instruction_request","subtype":"clear_instruction","category":"control","answer":"spring summer autumn winter","common_error":"","trap":""},
  # CONTROL: casual (10)
  {"id":"CA01","q":"Hello!","intent":"casual_greeting","subtype":"casual","category":"control","answer":"greeting","common_error":"","trap":""},
  {"id":"CA02","q":"Good morning!","intent":"casual_greeting","subtype":"casual","category":"control","answer":"greeting","common_error":"","trap":""},
  {"id":"CA03","q":"How are you?","intent":"casual_greeting","subtype":"casual","category":"control","answer":"greeting","common_error":"","trap":""},
  {"id":"CA04","q":"Thanks!","intent":"casual_greeting","subtype":"casual","category":"control","answer":"acknowledgment","common_error":"","trap":""},
  {"id":"CA05","q":"What's up?","intent":"casual_greeting","subtype":"casual","category":"control","answer":"greeting","common_error":"","trap":""},
  {"id":"CA06","q":"See you later!","intent":"casual_greeting","subtype":"casual","category":"control","answer":"farewell","common_error":"","trap":""},
  {"id":"CA07","q":"Have a nice day!","intent":"casual_greeting","subtype":"casual","category":"control","answer":"well-wish","common_error":"","trap":""},
  {"id":"CA08","q":"Tell me something interesting.","intent":"creative_request","subtype":"casual","category":"control","answer":"any fact","common_error":"","trap":""},
  {"id":"CA09","q":"I'm bored.","intent":"casual_greeting","subtype":"casual","category":"control","answer":"engagement","common_error":"","trap":""},
  {"id":"CA10","q":"Nice weather today!","intent":"casual_greeting","subtype":"casual","category":"control","answer":"agreement","common_error":"","trap":""},
]

# ── API ──────────────────────────────────────────────────────────────────────

def load_groq_key():
    key = os.environ.get("GROQ_API_KEY")
    if key: return key
    for p in [Path(".env"), Path.home()/".env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("GROQ_API_KEY="):
                    return line.split("=",1)[1].strip().strip('"\'')
    raise RuntimeError("GROQ_API_KEY not found")

def call_ollama(prompt, model, endpoint="http://localhost:11434", max_tokens=512, timeout=120):
    t0 = time.time()
    try:
        r = requests.post(f"{endpoint}/api/generate",
            json={"model":model,"prompt":prompt,"stream":False,"think":False,
                  "options":{"temperature":0.2,"num_predict":max_tokens}}, timeout=timeout)
        r.raise_for_status()
        return {"text":r.json().get("response",""),"latency_ms":int((time.time()-t0)*1000),"error":None}
    except Exception as e:
        return {"text":"","latency_ms":int((time.time()-t0)*1000),"error":str(e)}

def call_groq(prompt, model="openai/gpt-oss-20b", api_key=None, max_tokens=512):
    t0 = time.time()
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},
            json={"model":model,"messages":[{"role":"user","content":prompt}],
                  "temperature":0.2,"max_tokens":max_tokens}, timeout=60)
        r.raise_for_status()
        return {"text":r.json()["choices"][0]["message"]["content"],
                "latency_ms":int((time.time()-t0)*1000),"error":None}
    except Exception as e:
        return {"text":"","latency_ms":int((time.time()-t0)*1000),"error":str(e)}

def warmup_ollama(model, port):
    _log(f"  Warming {model} on port {port}...")
    call_ollama("warmup", model, f"http://localhost:{port}", max_tokens=1)
    time.sleep(1)

# ── Prompts ──────────────────────────────────────────────────────────────────

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
    return f"Original query: {query}\n\nDraft response:\n{draft}\n\nRefine for accuracy and clarity. Be concise."

CONDITIONS = ["baseline","fixed_qk_all","ism_adaptive","full_pipeline"]

def run_model(model_cfg, queries):
    results = []
    total = len(queries)*len(CONDITIONS)
    count = 0
    for cond in CONDITIONS:
        for q in queries:
            count += 1
            prompt = {"baseline":build_no_qk,"fixed_qk_all":build_fixed_qk,
                      "ism_adaptive":lambda qr,i=q["intent"]:build_ism_qk(qr,i),
                      "full_pipeline":lambda qr,i=q["intent"]:build_ism_qk(qr,i),
                     }[cond](q["q"])

            if model_cfg["backend"]=="ollama":
                r1 = call_ollama(prompt,model_cfg["model_id"],model_cfg["endpoint"])
            else:
                r1 = call_groq(prompt,model_cfg["model_id"],model_cfg.get("api_key"))
                time.sleep(0.5)

            p1,p1l = r1["text"],r1["latency_ms"]
            p2,p2l = "",0

            if cond=="full_pipeline" and not r1["error"]:
                p2p = build_pass2(p1,q["q"])
                ep2 = model_cfg.get("endpoint2") or model_cfg.get("endpoint","")
                if model_cfg["backend"]=="ollama":
                    r2 = call_ollama(p2p,model_cfg["model_id"],ep2,max_tokens=256)
                else:
                    r2 = call_groq(p2p,model_cfg["model_id"],model_cfg.get("api_key"),max_tokens=256)
                    time.sleep(0.5)
                p2,p2l = r2["text"],r2["latency_ms"]

            final = p2 if p2 else p1
            _log(f"  [{model_cfg['name']}:{count}/{total}] {cond}/{q['id']} ({p1l+p2l}ms) {'ERR' if r1.get('error') else 'OK'}")

            results.append({
                "query_id":q["id"],"query":q["q"],"category":q["category"],
                "subtype":q["subtype"],"intent":q["intent"],
                "answer":q["answer"],"common_error":q.get("common_error",""),
                "trap":q.get("trap",""),
                "model":model_cfg["name"],"condition":cond,
                "response":final,"pass1_text":p1,"pass2_text":p2,
                "pass1_latency_ms":p1l,"pass2_latency_ms":p2l,
                "total_latency_ms":p1l+p2l,"error":r1.get("error"),
            })
    return results

def main():
    groq_key = load_groq_key()
    print(f"GROQ_API_KEY: {groq_key[:8]}...")

    # Verify
    for port in [11434,11435]:
        r = call_ollama("ping","phi4-mini:latest",f"http://localhost:{port}",max_tokens=4)
        print(f"  Port {port}: {'OK' if not r['error'] else 'FAIL'}")
    r = call_groq("ping",api_key=groq_key,max_tokens=4)
    print(f"  Groq: {'OK' if not r['error'] else 'FAIL'}")

    models_ollama = [
        {"name":"phi4-mini","backend":"ollama","model_id":"phi4-mini:latest",
         "endpoint":"http://localhost:11434","endpoint2":"http://localhost:11435"},
        {"name":"qwen3.5-9b","backend":"ollama","model_id":"qwen3.5:9b",
         "endpoint":"http://localhost:11434","endpoint2":"http://localhost:11435"},
    ]
    model_groq = {"name":"gpt-oss-20b","backend":"groq",
                  "model_id":"openai/gpt-oss-20b","api_key":groq_key}

    print(f"\n=== Benchmark v2: {len(QUERIES)} queries x {len(CONDITIONS)} cond x 3 models = {len(QUERIES)*len(CONDITIONS)*3} ===\n")
    t0 = time.time()

    def run_ollama_seq():
        # Warmup phi4-mini on both GPUs
        warmup_ollama("phi4-mini:latest",11434)
        warmup_ollama("phi4-mini:latest",11435)
        time.sleep(3)
        r1 = run_model(models_ollama[0],QUERIES)
        # Warmup qwen on both GPUs
        warmup_ollama("qwen3.5:9b",11434)
        warmup_ollama("qwen3.5:9b",11435)
        time.sleep(3)
        r2 = run_model(models_ollama[1],QUERIES)
        return r1+r2

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_groq = ex.submit(run_model,model_groq,QUERIES)
        f_ollama = ex.submit(run_ollama_seq)
        all_results = []
        for f in as_completed([f_groq,f_ollama]):
            all_results.extend(f.result())

    elapsed = time.time()-t0
    out_dir = Path("benchmarks/results"); out_dir.mkdir(parents=True,exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_file = out_dir/f"qk_benchmark_v2_{ts}.json"
    with open(out_file,"w",encoding="utf-8") as f:
        json.dump(all_results,f,ensure_ascii=False,indent=2)

    print(f"\n=== Done in {elapsed:.0f}s | {len(all_results)} inferences → {out_file} ===")

if __name__=="__main__":
    main()
