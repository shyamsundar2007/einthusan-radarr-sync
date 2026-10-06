#!/bin/bash
# Einthusan-Radarr sync - runs twice daily
# Only notifies if movies were downloaded

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HOME/clawd/.env"

LOG_FILE="/tmp/einthusan-radarr-sync-$(date +%Y%m%d-%H%M%S).log"

# Telegram notification function
notify_telegram() {
    local message="$1"
    local BOT_TOKEN=$(op read "op://Server/Telegram Bot/credential")
    local CHAT_ID="${TELEGRAM_CHAT_ID:?TELEGRAM_CHAT_ID not set (see ~/clawd/.env)}"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" \
        -d "text=${message}" \
        -d "parse_mode=HTML" > /dev/null
}

# Run the sync script
~/apps/einthusan-radarr-sync/einthusan-radarr-sync --limit 3 2>&1 | tee "$LOG_FILE"

# Check if any movies were downloaded
# Note: grep -c already prints "0" (and exits 1) on no match, so the
# fallback must not also print — otherwise DOWNLOADED becomes "0\n0"
# and breaks the integer test below.
DOWNLOADED=$(grep -c "✓ Downloaded!" "$LOG_FILE" || true)

if [ "$DOWNLOADED" -gt 0 ]; then
    # Extract movie names. Keyed off the title line scanning FORWARD, not a fixed
    # offset back from "✓ Downloaded!": the sync prints a variable number of lines
    # between the two (✓ Found / 📥 Downloading), and the old `grep -B2` never reached
    # the title, so this grep matched nothing, returned 1, and set -e killed the
    # script *after* a successful download - turning every good run into a job
    # failure with no success notification. awk always exits 0, so a future
    # output-format change degrades to a missing name, not a dead job.
    MOVIES=$(awk '/^🎬 /{t=$0} /✓ Downloaded!/{if(++n<=5){sub(/^🎬 /,"• ",t); print t}}' "$LOG_FILE")
    notify_telegram "🎬 Einthusan downloaded ${DOWNLOADED} movie(s):
${MOVIES}"
fi

rm -f "$LOG_FILE"
