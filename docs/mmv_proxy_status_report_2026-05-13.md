# MMV Proxy 現状調査レポート (2026-05-13)

調査者: Claude Code (super-supervisor)
対象リポジトリ: `$HOME/デスクトップ/mobius_ai/MOBIUS_MMV`
ブランチ: `coverage-repair-alpha-beta` (HEAD `55f09e5`)

---

## MMV Proxy 現状

- **完成度: 完成 (production-grade, OpenAI 互換)**
- **エントリポイント:** [src/app/api.py](src/app/api.py) — `python -m src.app.api` (内部で `uvicorn.run(app, host=…, port=…)`)
- **起動方法:**
  - 推奨: `bash scripts/start_cline_api.sh` (デフォルト `MMV_API_PROFILE=high_capacity_practical`, bind `127.0.0.1:8088`)
  - 直接: `MMV_API_PROFILE=high_capacity_practical ~/デスクトップ/mobius_ai/venv313/bin/python -m src.app.api`
  - 必要環境変数: `GROQ_API_KEY` (リポジトリ直下の `.env` に存在することを確認済み — boolean のみ観測、値はログ・レスポンスに出ない)
  - 任意上書き: `MMV_API_BACKEND` / `MMV_API_MODEL` / `MOBIUS_API_HOST` / `MOBIUS_API_PORT` / `MMV_API_AUTH` (`off`/`key`) / `MMV_API_KEYS`
  - 依存: `fastapi 0.135.1` / `uvicorn 0.42.0` / `pydantic 2.12.5` (venv313 に揃っている)
- **ガバナンス層実装:**
  - **L0: 有** — Groq 経路では [addons/secretary/providers/groq_provider.py:80-117](addons/secretary/providers/groq_provider.py#L80-L117) `_build_system_prompt` が "Apply L0 Essentials silently" プレフィックスをツインインジェクション。ルーティング側 ([src/kernel/routing_engine.py](src/kernel/routing_engine.py)) は L0 v8.2 §9.1 (TVS_HIGH しきい値) を実装。
  - **ISM: 有** — [src/kernel/appraisal.py:20-32](src/kernel/appraisal.py#L20-L32) で `ISMProfile` をロードし intent classification を起動 (`raf/profile.py` ベース)。
  - **Box M: 有** — [src/kernel/routing_engine.py:37-41](src/kernel/routing_engine.py#L37-L41) で `MemoryIndexer` を open し、[L741-L752](src/kernel/routing_engine.py#L741-L752) で `ContextProcessor` (ME5 hybrid ambiguity resolver) を装着。実際にライブ呼び出しで `reason_codes` に `MEMORY_CONTEXT` が出ることを確認 (下記)。
  - 補助: Box X も `/v1/diagnostics/box_x` で読める (91 件、`curated_domain_pack`、すべて `fresh`)。
- **上流 LLM 転送: 実装** — `src/app/backend_routing.py` が `MMV_API_PROFILE` から `high_capacity_practical → Groq / openai/gpt-oss-120b` を解決し、[src/adapters/groq_inference_adapter.py](src/adapters/groq_inference_adapter.py) が `addons/secretary/providers/groq_provider.py` 経由で実際にリクエスト送信。`GROQ_API_KEY` 不在時は Ollama にフォールバックする設計 (`fallback_used=True` で診断に出る)。今回は `fallback_used=false` を確認。
- **ストリーミング: 対応** — [src/app/api.py:1004-1040](src/app/api.py#L1004-L1040) で `req.stream=true` 時に SSE (`text/event-stream`) でチャンク配信。ただし**実装上は engine.evaluate を 1 回回した後の repaired text を ~120 文字ごとに分割して送出する pseudo-streaming** であり、Groq 側のトークン単位ストリームを透過しているわけではない (`groq_inference_adapter.stream()` は単一チャンクを yield)。OpenAI クライアントから見たプロトコル互換性は完全。
- **最新 proxy 関連 commit:** `04bbfef` (2026-05-07) `fix(api): stabilize Cline post-read Japanese completions`
  - 周辺の proxy commit 系譜 (新しい順): `04bbfef → 1da5827 → fc82291 → 20e8b76 → 222fb5b (routes through configured high-capacity backend) → 9da8239 → 181db0f (initial OpenAI-compatible endpoint)`
- **動作確認: 成功**
  - `GET /healthz` → `{"status":"ok","phase":"g.12"}`
  - `GET /v1/models` → 3 モデル (`mobius-mmv-governed`, `mmv`, `mobius-mmv-cline`)
  - `POST /v1/chat/completions` (非ストリーム, `mobius_include_diagnostics=true`):
    - 入力: `"Reply with exactly one word: PING"`
    - 出力: `"PING"` (Groq 120B が実際に応答)
    - `mobius_diagnostics.backend = {"provider":"groq","model":"openai/gpt-oss-120b","profile":"high_capacity_practical","fallback_used":false,"source":"profile"}`
    - `mobius_diagnostics.route = "answer"`, `reason_codes = ["LOW_STAKES_STABLE","SUFFICIENTLY_SPECIFIED","BOX_PLAN_RECORDED","MEMORY_CONTEXT"]` — ガバナンス経路を実走していることを確認
  - `POST /v1/chat/completions` (`stream=true`): role delta → content delta `"OK"` → finish_reason `stop` → `[DONE]` の SSE 4 チャンクを取得、OpenAI フォーマット準拠

---

## Atlas Lite から呼び出す観点での評価

- **即座に Mode A (MMV proxy) として利用可能か: Yes**
- 接続パラメータ:
  - Provider: OpenAI Compatible
  - Base URL: `http://127.0.0.1:8088/v1`
  - API Key: 任意の文字列 (`MMV_API_AUTH=off` がデフォルト、認証無効)。`key` モードに切り替えるなら `MMV_API_AUTH=key` + `MMV_API_KEYS=<csv>` を export 後に再起動。
  - Model: `mobius-mmv-governed` / `mmv` / `mobius-mmv` / `mobius-mmv-cline` のいずれか (alias 解決済)
- 不足は無い。前提として以下が整っていれば即接続可能 (今回すべて充足):
  1. venv313 に fastapi / uvicorn / pydantic がある (済)
  2. `.env` に `GROQ_API_KEY` がある (済 — `high_capacity_practical` プロファイル使用時のみ必要; Ollama プロファイルなら不要)
  3. ポート 8088 が空いている (確認時は空き)
- 注意点:
  - **Streaming は pseudo-streaming** (engine 結果を後段で分割)。トークン単位の体感が必要な UI では遅延がブロッキングに感じられる可能性あり。OpenAI プロトコル互換性自体は問題なし。
  - Atlas Lite 側からの追加制御は `extra_body` 経由で可能 (`mobius_authority_profile_id` / `mobius_retrieval_profile_id` / `mobius_carryover_opt_out` / `mobius_include_diagnostics` / `mobius_session_id`)。
  - セッション継続が必要なら `mobius_session_id` を毎リクエストで送ること。未指定だと毎回 ephemeral session になる。
  - Box A 関連の Drive 操作は **このプロキシ経由では走らない** (CLAUDE.md の Hard rules: "MMV NEVER mutates Drive")。Drive 書き込みは Phase 2 ゲート。
