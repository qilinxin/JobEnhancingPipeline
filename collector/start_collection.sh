#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python="venv/bin/python"
cdp_url="http://127.0.0.1:9222"
chrome_profile="${LINKEDIN_CHROME_PROFILE:-$HOME/Library/Application Support/Chrome-LinkedIn-Debug}"
pg_host="${PGHOST:-localhost}"
pg_port="${PGPORT:-5432}"

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

[[ -x "$python" ]] || fail "The project virtual environment is missing. See docs/RUN_LINKEDIN_COLLECTION.md."

browser_only=false
source=linkedin
options=()
while (($#)); do
  arg="$1"
  shift
  case "$arg" in
    -h|--help)
      printf '%s\n\n' "Usage: ./collector/start_collection.sh [--browser-only] [collector options]" \
        "The launcher opens LinkedIn, Indeed, and SEEK searches in debugging Chrome."
      exec "$python" run.py --help
      ;;
    --tab|--tab=*|--cdp|--cdp=*|--list-tabs)
      fail "This launcher selects the tab and uses port 9222. Run run.py directly for custom browser options."
      ;;
    --browser-only)
      browser_only=true
      ;;
    --source)
      (($#)) || fail "Provide linkedin, indeed, or seek after --source."
      source="$1"
      shift
      ;;
    --source=*)
      source="${arg#*=}"
      ;;
    *)
      options+=("$arg")
      ;;
  esac
done
case "$source" in
  linkedin|indeed|seek) ;;
  *) fail "Choose linkedin, indeed, or seek as the source." ;;
esac

wait_for() {
  local description="$1"
  shift
  local attempt
  for ((attempt = 0; attempt < 30; attempt++)); do
    if "$@"; then
      return 0
    fi
    sleep 1
  done
  fail "$description did not become ready. See docs/RUN_LINKEDIN_COLLECTION.md."
}

postgres_ready() {
  pg_isready -q -t 1 -h "$pg_host" -p "$pg_port"
}

chrome_ready() {
  curl --noproxy '*' -fsS --max-time 1 "$cdp_url/json/version" 2>/dev/null |
    "$python" -c 'import json, sys; sys.exit(not json.load(sys.stdin).get("webSocketDebuggerUrl"))' 2>/dev/null
}

if ! chrome_ready; then
  open -na "Google Chrome" --args \
    --remote-debugging-port=9222 \
    --user-data-dir="$chrome_profile" \
    --new-window "about:blank"
  wait_for "Chrome DevTools on port 9222" chrome_ready
fi

"$python" -m collector.search_tabs "$cdp_url"
if "$browser_only"; then
  exit 0
fi

command -v pg_isready >/dev/null || fail "pg_isready is missing from PATH. Add the PostgreSQL tools to PATH."
if ! postgres_ready; then
  case "$pg_host" in
    localhost|127.0.0.1|::1) ;;
    *) fail "PostgreSQL at $pg_host:$pg_port is unavailable. Start it on its host and try again." ;;
  esac
  command -v brew >/dev/null || fail "Homebrew is required to start the local PostgreSQL service."
  brew services start postgresql@17
  wait_for "PostgreSQL at $pg_host:$pg_port" postgres_ready
fi
printf 'PostgreSQL is accepting connections at %s:%s.\n' "$pg_host" "$pg_port"

printf '\nReview the %s search tab in debugging Chrome and sign in if needed.\n' "$source"
printf '%s' "Press Enter once the search results are open: "
IFS= read -r _ || fail "An interactive terminal is required to select the search tab."
"$python" run.py --source "$source" --list-tabs

printf '%s search tab number [1]: ' "$source"
IFS= read -r tab || fail "No search tab was selected."
tab="${tab:-1}"
[[ "$tab" =~ ^[1-9][0-9]*$ ]] || fail "Enter a positive search tab number."
exec "$python" run.py --source "$source" --tab "$tab" ${options[@]+"${options[@]}"}
