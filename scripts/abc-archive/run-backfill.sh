#!/bin/zsh
# One-off ABC report backfill, started with `launchctl kickstart gui/$(id -u)/org.example.sfhp.abc-backfill`.
# Keeps the Mac awake while it runs, resumes where a previous run stopped, and packs + verifies the raw pages
# into yearly archives only when the run completes. Stops (no retry) on 403/429/timeouts.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

APP_REPO="${APP_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
DATA_REPO="${DATA_REPO:?set DATA_REPO to a git checkout of your archive data repository (kept outside this repo)}"
STAGING="${STAGING:-$DATA_REPO-staging}"
BACKFILL_FROM="${BACKFILL_FROM:-2019-01-01}"
ENV_FILE="${ABC_ARCHIVE_ENV_FILE:-$HOME/.config/sfhp/abc-archive.env}"
PY="$APP_REPO/apps/api/.venv/bin/python"

[[ -f "$ENV_FILE" ]] && set -a && source "$ENV_FILE" && set +a
cd "$APP_REPO/packages/precedent"
echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) backfill start (from $BACKFILL_FROM)"
/usr/bin/caffeinate -is "$PY" -m precedent.abc_backfill run --repo "$DATA_REPO" --staging "$STAGING" \
  --from "$BACKFILL_FROM" --commit --push
code=$?
if [[ $code -eq 0 ]]; then
  echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) packing raw pages"
  /usr/bin/caffeinate -is "$PY" -m precedent.abc_backfill pack --repo "$DATA_REPO" --staging "$STAGING"
  code=$?
fi
"$PY" -m precedent.abc_backfill status --repo "$DATA_REPO" --staging "$STAGING"
echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) backfill finished, exit $code"
exit $code
