#!/bin/bash
# Einthusan cookie refresh - runs twice daily
# Only notifies on failure

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HOME/clawd/.env"

# Run the login script, retrying once on failure (Einthusan is occasionally slow)
MAX_ATTEMPTS=2
RETRY_DELAY=30
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    if output=$(~/apps/einthusan-radarr-sync/einthusan-login 2>&1); then
        echo "$output"
        echo "$(date): Cookie refresh successful (attempt $attempt)"
        exit 0
    fi
    echo "$(date): Attempt $attempt/$MAX_ATTEMPTS failed. Output:" >&2
    echo "$output" >&2
    [ "$attempt" -lt "$MAX_ATTEMPTS" ] && sleep "$RETRY_DELAY"
done

echo "❌ Einthusan cookie refresh failed after $MAX_ATTEMPTS attempts. Check manually." >&2
exit 1
