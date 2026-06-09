# Pattern Library — T Authoring Workflow Guide

**Audience**: Taiko (project lead, MMV sole architect)
**Purpose**: Author 2+ patterns to satisfy Phase 1 spec 5.2.3 success criterion before Phase 2.
**Date**: 2026-04-25 (Phase 1 closed)
**Spec reference**: `docs/PATTERN_LIBRARY_SPEC_v1_3.md` Section 2.3 (schema), Section 5.6.6 (workflow)

---

## 0. なぜこの guide が必要か

Phase 1 の Web UI には authoring form が無い (Phase 2 deliverable)。Phase 1 の success criterion `T が Web UI で 2+ patterns を実際に authoring` を達成する暫定 path が JSONL 直接 edit。本 guide はその workflow を documented form で提供する。

完了条件:
- 2+ 個の新 pattern が `config/pattern_library/*.jsonl` に存在
- Schema validation pass
- FAISS index に登録済み
- Web UI で表示可能
- git commit 済み

所要時間: 1 pattern あたり 15-30 分。慣れたら 10 分以内。

---

## 1. 推奨 author 候補 (T の judgment 反映用)

Phase 1 の 10 seed patterns は self_reference (5) + conceptual_explain (5) のみ。Library を T's domain で enrich するために、以下の topic から 2+ を選ぶことを推奨:

### 候補 A: correction handling (F4b 対応)

| 候補 ID | intent | rationale |
|---|---|---|
| `pat_correction_factual_001` | reject_factual_claim | "no, that's wrong" / "違います" / "不对" 等。F4b の context 失効問題を library 側で吸収 |
| `pat_correction_self_ref_001` | correct_self_understanding | "I'm not asking about you" / "あなたのことではない" 等。Identity 関連 correction |

### 候補 B: self_reference 追加 (Phase 1 で漏れた intent)

| 候補 ID | intent | rationale |
|---|---|---|
| `pat_self_ref_creator_001` | describe_creator | "Who made you" / "誰が作った" / "你是谁创造的" 等。Phase 1 self_ref 5 patterns に未 covered |
| `pat_self_ref_evolution_001` | describe_evolution | "How did you evolve" / "どう進化した" 等。MMV の自己進化的特性に関する query |

### 候補 C: T-specific concept (MOBIUS 固有)

| 候補 ID | intent | rationale |
|---|---|---|
| `pat_concept_explain_qk_001` | explain_question_kernel | Question Kernel (QK) は MMV の中核 governance layer。説明 query を library 側で primary route |
| `pat_concept_explain_rsg_001` | explain_reflective_semantic_gravity | RSG は Reflective Economics の core construct |
| `pat_concept_explain_eal_001` | explain_evidence_adjudication_layer | EAL は L0 で言及されるが existing pattern で direct match していない |

### 候補 D: factual_inquiry の pattern (Phase 1 で 0 個)

| 候補 ID | intent | rationale |
|---|---|---|
| `pat_factual_definition_001` | ask_for_definition | "What is X" / "X とは" / "X 是什么" 等。Definition 系 query は box_w に route するべき |
| `pat_factual_comparison_001` | compare_entities | "X vs Y" / "X と Y の違い" 等 |

---

## 2. Workflow steps

### Step 1: 環境準備

```bash
# venv activate
mobius
# (= source ~/デスクトップ/mobius_ai/venv313/bin/activate)

cd ~/デスクトップ/mobius_ai/MOBIUS_MMV/

# 現状確認
git status
git log --oneline -3
# 期待: 0b03f33 が HEAD (Phase B 完了 commit)

# Existing patterns を browse して reference を確認
ls config/pattern_library/
# self_reference.jsonl, conceptual_explain.jsonl が見えるはず
```

### Step 2: Reference pattern を読む

新 pattern の schema reference として既存 pattern を 1 つ読む:

```bash
# conceptual_explain の中の 1 pattern を pretty-print
python3 -c "
import json
with open('config/pattern_library/conceptual_explain.jsonl') as f:
    for line in f:
        if line.strip():
            obj = json.loads(line)
            print(json.dumps(obj, indent=2, ensure_ascii=False))
            break
"
```

これで schema の全 field が確認できる。

### Step 3: 新 pattern を draft

`/tmp/new_pattern.json` に draft (single object、まだ JSONL ではない):

```bash
cat > /tmp/new_pattern.json <<'EOF'
{
  "id": "pat_correction_factual_001",
  "version": "1.0",
  "lang": "en",
  "topic": "correction",
  "intent": "reject_factual_claim",
  "concepts": ["~negation", "~correction"],
  "priority": 100,
  "examples": [
    "No, that's wrong",
    "That's incorrect",
    "Actually that's not right",
    "You're mistaken about that",
    "That's not accurate",
    "I disagree with that",
    "That's a misconception",
    "You have it wrong",
    "Let me correct you"
  ],
  "negative_examples": [
    "No problem",
    "No worries",
    "Wrong question",
    "That's a wrong number"
  ],
  "context_required": null,
  "context_excluded": [],
  "route": {
    "primary_box": "box_0",
    "exclude_boxes": [],
    "synthesis_mode": "correction_acknowledgment"
  },
  "tags": ["correction", "factual_dispute"],
  "cross_lingual_test_queries": [
    {"lang": "ja", "query": "違います、それは間違っています", "expected_match": true, "min_cosine": 0.65},
    {"lang": "ja", "query": "間違い電話です", "expected_match": false},
    {"lang": "zh", "query": "不对,那是错的", "expected_match": true, "min_cosine": 0.65},
    {"lang": "zh", "query": "错号", "expected_match": false}
  ],
  "lifecycle": {
    "hit_count": 0,
    "last_hit_date": null,
    "last_xling_pass_rate": null,
    "audit_status": "active",
    "deletion_proposals": [],
    "history": [
      {
        "timestamp": "2026-04-25T22:00:00Z",
        "event": "created",
        "actor": "taiko",
        "detail": "Phase 1 closure: T-authored pattern for F4b correction handling"
      }
    ]
  },
  "origin": {
    "type": "manual",
    "evolution_log_entry": 22,
    "date": "2026-04-25",
    "scenario_id": null
  },
  "deprecated": false
}
EOF
```

注意点:

- **id**: pattern `^pat_[a-z_]+_\d{3}$` に match する必要あり (Pydantic validator)
- **lang**: Phase 1 では `"en"` 固定
- **examples**: 5-15 個、推奨 8-10 個
- **negative_examples**: 任意だが推奨。disambiguation 効果が大きい
- **cross_lingual_test_queries**: minimum 4、JA 2+ ZH 2+ 必須 (validator が reject)
- **route.primary_box**: 9-box namespace (`box_0`-`box_7`, `box_w`) のみ
- **lifecycle.history**: 必ず `created` event を 1 つ
- **origin.type**: T author なら `"manual"`
- **timestamp**: ISO-8601 with `Z` (UTC)

### Step 4: 単体 schema validation (commit 前に validate)

```bash
python3 -c "
import json
import sys
sys.path.insert(0, '.')
from src.retrieval.pattern_schema import Pattern

with open('/tmp/new_pattern.json') as f:
    obj = json.load(f)

try:
    p = Pattern(**obj)
    print(f'PASS: {p.id} schema valid')
except Exception as e:
    print(f'FAIL: {e}')
"
```

エラーが出たら field を見直し。よくある失敗:

- `cross_lingual_test_queries` の JA / ZH count 不足 → 各 2+ 必要
- `examples` が 5 未満 → minimum 5
- `route.primary_box` が typo (例: `"box0"` ではなく `"box_0"`)
- timestamp が ISO-8601 format でない
- id が pattern match しない (例: `"pat_correction_001"` は OK だが `"pat-correction-001"` はダメ)

### Step 5: JSONL に append

新 pattern が correction topic なら新ファイル作成:

```bash
# 新 topic の場合
mv /tmp/new_pattern.json /tmp/new_pattern_compact.json
python3 -c "
import json
with open('/tmp/new_pattern.json') as f:
    obj = json.load(f)
with open('/tmp/new_pattern_compact.json', 'w') as f:
    f.write(json.dumps(obj, ensure_ascii=False) + '\n')
"
mv /tmp/new_pattern_compact.json config/pattern_library/correction.jsonl
```

既存 topic に追加なら append:

```bash
# self_reference 既存ファイルに append (例: pat_self_ref_creator_001 を追加する場合)
python3 -c "
import json
with open('/tmp/new_pattern.json') as f:
    obj = json.load(f)
with open('config/pattern_library/self_reference.jsonl', 'a') as f:
    f.write(json.dumps(obj, ensure_ascii=False) + '\n')
"
```

### Step 6: Schema 一括 validation

```bash
pytest tests/retrieval/test_pattern_schema.py -v
# 期待: 全 pass (新 pattern も含めて)
```

もし fail なら step 4 に戻る。

### Step 7: FAISS index rebuild

```bash
CUDA_VISIBLE_DEVICES=0 python scripts/build_pattern_index.py
# 期待: "Index built. N patterns indexed." (N が増えていること)
```

### Step 8: Golden set re-evaluate (regression check)

```bash
python scripts/golden_set_eval.py
# 期待: target topic accuracy が前回と同等以上 (96/100 を維持 or 向上)
```

新 pattern が既存 pattern と conflict すると accuracy 低下する可能性。-3% 以上の低下なら新 pattern を見直し。

### Step 9: Web UI で確認

```bash
MOBIUS_PATTERN_LIBRARY=1 python -m src.ui.library_inspector.app &
# Browser: http://127.0.0.1:5000
```

新 pattern が `Browse` ページの該当 topic に表示されることを確認。Click で detail page を開き、各 field が正しく表示されることを確認。

特に確認すべき:
- Examples が想定通り並んでいる
- Negative examples が disambiguation として spread している
- Cross-lingual test queries が 4 件以上
- Lifecycle.history に creation entry
- Origin が `manual` で T が actor

### Step 10: Verify (cross-lingual test) 実行

Web UI から該当 pattern の detail page → `Run cross-lingual test` button を click。

期待: pass rate ≥ 70% (Phase 1 で 100% target)。失敗 query があれば examples / cross_lingual_test_queries の design を見直し。

### Step 11: 33-scenario harness regression check

```bash
# Web UI を停止してから
pkill -f "library_inspector.app"

# Advisory off (default) で regression check
python scripts/run_33_scenarios.py --quiet
# 期待: ≥ 28 (Phase B 29 から -1 tolerance, Phase A 31 から -3 tolerance)
```

これは optional だが、新 pattern が legacy routing と干渉していないことの確認。

### Step 12: git commit

```bash
git add config/pattern_library/<topic>.jsonl
git status  # 確認
git diff --cached  # diff 確認

git commit -m "feat(pattern_lib): add pat_correction_factual_001 (T-authored)

Phase 1 success criterion (spec 5.2.3 'T authors 2+ patterns'):
- Topic: correction
- Intent: reject_factual_claim
- Origin: manual (T author)
- Cross-lingual test queries: 4 (JA 2 + ZH 2)
- Examples: 9 EN samples
- Negative examples: 4 (disambiguation against 'no problem' etc.)

Schema validated, FAISS index rebuilt, golden set regression none.
"
```

### Step 13: 2nd pattern を author

Steps 3-12 を繰り返し。少なくとも 2 patterns 完了で Phase 1 success criterion met。

---

## 3. Pattern design tips

### 3.1 Examples の design

良い examples:
- 5-15 個、推奨 8-10
- 同 intent の linguistic variation (formal, casual, partial query)
- 特定単語に依存しない (single keyword に過適合させない)
- 各 example は完結した query (fragment は避ける)

悪い examples:
- 全 example が同じ語彙構造 ("Tell me X" だけ 10 個)
- Single keyword に依存 ("X" を含めば必ず match のような)
- 文法的に不完全な fragment
- intent の boundary を曖昧にする (例: question + statement の混在)

### 3.2 Negative examples の design

Negative examples は false positive を block する。Phase 1 self_ref pattern の例:

```
正の examples:
- "What are your characteristics"
- "Describe yourself"

Negative examples:
- "What is a Möbius strip" (mathematical concept)
- "Tell me about Ultraman Mobius" (anime character)
- "What is the Mobius company" (corporate disambiguation)
- "Möbius transformation in mathematics" (different math concept)
```

これらは `Möbius` 単語を含むが intent が異なる query。Library が "Möbius" 単語だけで self_ref に match すると Wikipedia disambiguation に fall through せず誤 routing。Negative examples で blocked。

T の domain knowledge が最も活きる field。

### 3.3 Cross-lingual queries の design

Phase 1 schema validator は最低 JA 2 + ZH 2。実際は 6-8 個推奨 (各言語 3-4 個)。

各 query に `expected_match`:
- `true`: cross-lingual で hit するべき query (positive)
- `false`: similar 表面語彙だが intent 異なる (negative)

`min_cosine` は positive query のみに設定 (e.g. 0.65)。cosine がこれ未満なら verify が fail を返す。

### 3.4 Route の design

`primary_box`:
- `box_0`: identity / self-ref / governance concepts (MMV-internal)
- `box_w`: Wikipedia / general factual (cross-lingual ME5)
- `box_1` - `box_7`: 用途別 (spec Section 2.2 確認)

`exclude_boxes`: 該当 query で絶対に consult しないべき box。例:
- self_ref pattern → `["box_w"]` (Wikipedia 曖昧さ回避を block)

`synthesis_mode`: spec で定義された synthesis template。新 mode を invent すると routing engine 側の handler が無いので注意。

---

## 4. Troubleshooting

### Q: Schema validation で `cross_lingual_test_queries: too short` エラー

A: JA 2 個 + ZH 2 個が最小。`langs.count("ja") < 2 or langs.count("zh") < 2` を満たすこと。

### Q: `id` validation エラー

A: pattern `^pat_[a-z_]+_\d{3}$`。例: `pat_correction_factual_001` OK、`pat-correction-001` NG、`pat_correction_001_v2` NG (suffix `_v2` は許容外)。

### Q: FAISS index rebuild で "ME5 model load failed"

A: Network 接続確認。Model は HuggingFace から download される (初回のみ)。
```bash
python3 -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('intfloat/multilingual-e5-large')"
```

### Q: Golden set accuracy が low下した

A: 新 pattern の examples が既存 pattern と conflict している。Confusion matrix を確認:
```bash
python scripts/golden_set_eval.py --verbose
```
具体的にどの query が新 pattern に誤 hit しているか identify。Negative examples を追加するか、examples を絞り込む。

### Q: Web UI で新 pattern が表示されない

A:
1. FAISS index rebuild 忘れ → Step 7 を実行
2. Web UI を再起動 (`pkill -f library_inspector` → 再 launch)
3. JSONL ファイルが正しい topic ファイルに保存されているか確認

### Q: 33-scenario が regression

A: 新 pattern が legacy routing path に干渉。ただし advisory off (default) なら原則 影響しないはず。-3 以上 regression なら:
1. Pattern を library から removed (jsonl から削除、index rebuild)
2. 33-scenario を再実行、baseline に戻ることを確認
3. 新 pattern の design を見直し (恐らく overly broad examples)

---

## 5. Phase 1 closure checklist

2+ patterns を author 後、以下を確認して Phase 1 を closing:

- [ ] 2+ 個の新 pattern が `config/pattern_library/*.jsonl` に存在
- [ ] 全 pattern が `pytest tests/retrieval/test_pattern_schema.py -v` で pass
- [ ] FAISS index rebuilt (`scripts/build_pattern_index.py` 成功)
- [ ] Golden set evaluation で accuracy 維持または向上
- [ ] Web UI で全 pattern が browse / detail / verify 可能
- [ ] 33-scenario harness で regression なし (-3 以下)
- [ ] git commit ログに新 pattern の追加が記録
- [ ] `docs/PATTERN_LIBRARY_PHASE1_RESULTS.md` を update して T authoring 達成を記録
  - Section "Web UI dogfooding" に "T authored N patterns: [list]" を追加
  - Phase 1 success criterion 5.2.3 全項 met と confirm

完了したら Phase 1 fully closed。Phase 2 autonomous prompt に進める。

---

## 6. 次のステップ

T authoring が完了したら:
- Phase 2 autonomous prompt を Claude Code に投入 (`CLAUDE_CODE_PHASE_2_AUTONOMOUS_PROMPT.md`)
- Phase 2 は auto-generation pipeline + golden set 200 + C-2 fix + selective primary mode を含む
- Detailed plan: spec v1.3 Section 10.2 (12-15 commits, 3-4 sessions)

Phase 2 開始前の T 必須行動:
- Patent attorney review schedule の確認 (Phase 2 release path での mandatory)
- 新 pattern の T review (Claude Code 認知が反映されているか)

Phase 2 中の T optional 行動:
- Library Inspector dogfooding (新規 pattern 追加時の workflow)
- Golden set 200 拡張への domain knowledge contribution

---

**End of Authoring Guide**

質問・トラブル時は `docs/PATTERN_LIBRARY_SPEC_v1_3.md` Section 5.6.6 を参照。Spec が authoritative。
