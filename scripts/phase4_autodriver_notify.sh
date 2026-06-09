#!/usr/bin/env bash
# Phase 4 autodriver notification helper.
#
# Sends a desktop notification (notify-send) AND appends to the log file.
# notify-send needs DBUS_SESSION_BUS_ADDRESS to fire from a cron job, so
# we set it explicitly to the user's runtime bus.
#
# Usage:
#   phase4_autodriver_notify.sh <urgency> <title> <body>
#
# urgency: low | normal | critical
#
# T can swap this script for an email/Slack/Discord variant — the wrapper
# just calls "phase4_autodriver_notify.sh".
set -euo pipefail

URGENCY="${1:-normal}"
TITLE="${2:-Phase 4 autodriver}"
BODY="${3:-(empty)}"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$REPO/.phase4_autodriver.log"

# Ensure UID-derived runtime path even when invoked from cron.
if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
    UID_NUM="$(id -u)"
    if [[ -S "/run/user/$UID_NUM/bus" ]]; then
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$UID_NUM/bus"
    fi
fi
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# Best-effort notify-send. Failure does not abort.
if command -v notify-send >/dev/null 2>&1; then
    notify-send -u "$URGENCY" "$TITLE" "$BODY" 2>>"$LOG" || true
fi

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '%s NOTIFY[%s] %s :: %s\n' "$ts" "$URGENCY" "$TITLE" "$BODY" >>"$LOG"
