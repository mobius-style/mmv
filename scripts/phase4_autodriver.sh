#!/usr/bin/env bash
# Phase 4 autodriver — chains Claude Code conversations to drive
# Phase 4 v2.1 to closure without T re-pasting the self-trigger.
#
# Flow (per cron tick):
#   1. Acquire flock (skip if a prior tick is still running)
#   2. Pre-checks: state.disabled, GPU slot 1 idle for embedding, token cap
#   3. Locate latest handover doc, extract self-trigger paste-block
#   4. Pre-update state from current handover (catches HARD STOP markers
#      added by the previous conversation)
#   5. Invoke `claude -p` with the trigger as prompt; bypass permissions
#      so internal tool calls don't hang on a TTY-less prompt
#   6. After completion, re-locate the (possibly newer) handover doc and
#      update state. Fire notifications for milestones / token thresholds /
#      hard-stop markers.
#
# State + lock + log live in repo root (gitignored):
#   .phase4_autodriver_state.json
#   .phase4_autodriver.lock
#   .phase4_autodriver.log
#
# Modes:
#   phase4_autodriver.sh                  — full run (default)
#   phase4_autodriver.sh --dry-run        — extract trigger + show plan, no claude call
#   phase4_autodriver.sh --status         — print state JSON, exit
#   phase4_autodriver.sh --enable         — clear state.disabled
#   phase4_autodriver.sh --disable=REASON — set state.disabled
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

# Make $HOME/.local/bin (claude) reachable when invoked from cron.
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export HF_HOME="${HF_HOME:-$HOME/デスクトップ/mobius_ai/huggingface}"

VENV_PY="$HOME/デスクトップ/mobius_ai/venv313/bin/python"
HELPERS="$REPO/scripts/phase4_autodriver_helpers.py"
export NOTIFY="$REPO/scripts/phase4_autodriver_notify.sh"
STATE="$REPO/.phase4_autodriver_state.json"
LOCK="$REPO/.phase4_autodriver.lock"
LOG="$REPO/.phase4_autodriver.log"
DOCS="$REPO/docs"

# ---- Config: tweak via env override --------------------------------------
# Per-conversation budget cap (USD). T sets via PHASE4_AUTODRIVER_BUDGET.
BUDGET_USD="${PHASE4_AUTODRIVER_BUDGET:-15}"
# Override claude binary path if needed.
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
# How long any single conversation is allowed to run before SIGTERM (seconds).
# Sized to exceed a typical full Phase 4 conversation including FAISS rebuilds
# and golden runs. T can lower via PHASE4_AUTODRIVER_TIMEOUT.
CONV_TIMEOUT_S="${PHASE4_AUTODRIVER_TIMEOUT:-21600}"   # 6h
# --------------------------------------------------------------------------

mode="run"
disable_reason=""
for arg in "$@"; do
    case "$arg" in
        run|--run) mode="run" ;;
        --dry-run) mode="dry-run" ;;
        --status)  mode="status" ;;
        --enable)  mode="enable" ;;
        --disable=*) mode="disable"; disable_reason="${arg#--disable=}" ;;
        -h|--help)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { printf '%s %s\n' "$(ts)" "$*" >>"$LOG"; }
notify() { "$NOTIFY" "$1" "$2" "$3" || true; }

ensure_state() {
    if [[ ! -f "$STATE" ]]; then
        "$VENV_PY" "$HELPERS" init-state "$STATE" >/dev/null
        log "init: created $STATE"
    fi
}

case "$mode" in
    status)
        ensure_state
        "$VENV_PY" "$HELPERS" read-state "$STATE"
        exit 0
        ;;
    enable)
        ensure_state
        "$VENV_PY" "$HELPERS" set-disabled "$STATE" false --reason "manual_enable"
        log "manual: enabled"
        exit 0
        ;;
    disable)
        ensure_state
        "$VENV_PY" "$HELPERS" set-disabled "$STATE" true --reason "${disable_reason:-manual_disable}"
        log "manual: disabled (${disable_reason:-manual_disable})"
        exit 0
        ;;
esac

# Acquire lock. Non-blocking: if a prior tick is still running, exit cleanly.
exec 9>"$LOCK"
if ! flock -n 9; then
    log "skip: another autodriver tick is running"
    exit 0
fi

ensure_state

# 1. Disabled?
disabled="$("$VENV_PY" "$HELPERS" check-thresholds "$STATE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["disabled"])')"
if [[ "$disabled" == "True" ]]; then
    log "skip: state.disabled=True"
    exit 0
fi

# 2. Phase 4 closed already?
closed="$("$VENV_PY" "$HELPERS" check-thresholds "$STATE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["phase4_closed"])')"
if [[ "$closed" == "True" ]]; then
    log "skip: phase4_closed=True"
    exit 0
fi

# 3. GPU pre-check: slot 2 (GPU index 1) must be idle for embedding work.
#    Threshold: < 1024 MiB used and < 10% utilization. Ollama on slot 2 is
#    OK (not embedding work), but a phase4 driver instance with ME5 loaded
#    on slot 2 would saturate. We treat any active compute >= 1GB as "busy"
#    and skip — wrapper is conservative.
slot2_mem="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits --id=1 2>/dev/null | tr -d ' ' || echo "0")"
slot2_util="$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits --id=1 2>/dev/null | tr -d ' ' || echo "0")"
if [[ -n "$slot2_mem" ]] && [[ "$slot2_mem" -ge 6000 ]] && [[ "$slot2_util" -ge 30 ]]; then
    # Heavy compute on slot 2 — likely an embedding job already underway.
    log "skip: GPU slot 2 busy (mem=${slot2_mem}MiB util=${slot2_util}%)"
    exit 0
fi

# 4. Locate latest handover doc.
HANDOVER="$("$VENV_PY" "$HELPERS" find-latest-handover "$DOCS" || true)"
if [[ -z "$HANDOVER" ]] || [[ ! -f "$HANDOVER" ]]; then
    log "abort: no handover doc found in $DOCS"
    notify critical "Phase 4 autodriver" "No handover doc found — aborting"
    exit 1
fi
log "handover: $HANDOVER"

# 5. Pre-update state (catches HARD STOP / closure markers from previous run).
PRE_UPDATE_JSON="$("$VENV_PY" "$HELPERS" update-state "$STATE" --from-handover "$HANDOVER")"
echo "$PRE_UPDATE_JSON" >>"$LOG"

# Fire notifications from pre-update step.
echo "$PRE_UPDATE_JSON" | python3 -c '
import json, sys, subprocess, os
data = json.load(sys.stdin)
for note in data.get("notify", []):
    urg = "critical" if ("HARD STOP" in note or "PHASE 4 CLOSED" in note) else "normal"
    subprocess.run([os.environ["NOTIFY"], urg, "Phase 4 autodriver", note], check=False)
' || true

# Re-check disabled after pre-update.
disabled="$("$VENV_PY" "$HELPERS" check-thresholds "$STATE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["disabled"])')"
if [[ "$disabled" == "True" ]]; then
    log "stop: pre-update flipped state.disabled (hard stop or closure)"
    exit 0
fi

# 6. Extract trigger paste-block.
TRIGGER_FILE="$(mktemp /tmp/phase4_autodriver_trigger.XXXXXX.txt)"
trap 'rm -f "$TRIGGER_FILE"' EXIT
if ! "$VENV_PY" "$HELPERS" extract-trigger "$HANDOVER" >"$TRIGGER_FILE" 2>>"$LOG"; then
    log "abort: extract-trigger failed for $HANDOVER"
    notify critical "Phase 4 autodriver" "Trigger extraction failed for $(basename "$HANDOVER")"
    exit 1
fi
trigger_lines="$(wc -l <"$TRIGGER_FILE")"
log "trigger extracted: ${trigger_lines} lines from $HANDOVER"

if [[ "$mode" == "dry-run" ]]; then
    log "dry-run: would invoke $CLAUDE_BIN with trigger ($trigger_lines lines, budget=\$$BUDGET_USD, timeout=${CONV_TIMEOUT_S}s)"
    echo "=== DRY-RUN PLAN ==="
    echo "  handover:   $HANDOVER"
    echo "  trigger:    $TRIGGER_FILE ($trigger_lines lines)"
    echo "  invocation: $CLAUDE_BIN -p --permission-mode bypassPermissions \\"
    echo "                --add-dir $REPO --max-budget-usd $BUDGET_USD --no-session-persistence \\"
    echo "                --output-format text \\"
    echo "                < $TRIGGER_FILE"
    echo "  state file: $STATE"
    "$VENV_PY" "$HELPERS" read-state "$STATE"
    exit 0
fi

# 7. Invoke claude -p. Bypass permissions so the conversation runs unattended.
#    --no-session-persistence: each tick is a fresh conversation.
#    --add-dir REPO: tool access scoped to the project.
#    --max-budget-usd: cap per-conversation spend.
#    Pipe trigger via stdin (text input format).
log "invoke: claude -p (budget=\$$BUDGET_USD, timeout=${CONV_TIMEOUT_S}s)"
inv_log="$REPO/.phase4_autodriver_invoke_$(date -u +%Y%m%dT%H%M%SZ).log"

set +e
timeout --signal=SIGTERM --kill-after=120 "$CONV_TIMEOUT_S" \
    "$CLAUDE_BIN" -p \
        --permission-mode bypassPermissions \
        --add-dir "$REPO" \
        --max-budget-usd "$BUDGET_USD" \
        --no-session-persistence \
        --output-format text \
        <"$TRIGGER_FILE" >"$inv_log" 2>&1
exit_code=$?
set -e

case "$exit_code" in
    0)   log "claude exit 0 (ok); inv_log=$inv_log" ;;
    124) log "claude killed by timeout after ${CONV_TIMEOUT_S}s; inv_log=$inv_log"
         notify critical "Phase 4 autodriver" "Claude conversation timed out after ${CONV_TIMEOUT_S}s — see $inv_log" ;;
    *)   log "claude exit $exit_code (non-zero); inv_log=$inv_log"
         notify normal "Phase 4 autodriver" "Claude exited $exit_code — see $inv_log" ;;
esac

# 8. Post-update state from new handover (may be the same doc if conversation
#    didn't write a new one — that's not necessarily a failure but is logged).
NEW_HANDOVER="$("$VENV_PY" "$HELPERS" find-latest-handover "$DOCS" || true)"
if [[ -n "$NEW_HANDOVER" ]] && [[ "$NEW_HANDOVER" != "$HANDOVER" ]]; then
    log "post: new handover detected: $NEW_HANDOVER"
    POST_JSON="$("$VENV_PY" "$HELPERS" update-state "$STATE" --from-handover "$NEW_HANDOVER")"
    echo "$POST_JSON" >>"$LOG"
    echo "$POST_JSON" | python3 -c '
import json, sys, subprocess, os
data = json.load(sys.stdin)
for note in data.get("notify", []):
    urg = "critical" if ("HARD STOP" in note or "PHASE 4 CLOSED" in note) else "normal"
    subprocess.run([os.environ["NOTIFY"], urg, "Phase 4 autodriver", note], check=False)
' || true
else
    log "post: no new handover doc; state unchanged"
fi

log "tick complete (exit=$exit_code)"
exit 0
