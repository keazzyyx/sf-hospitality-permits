#!/bin/zsh
# Daily ABC report archive, run by launchd (org.example.sfhp.abc-archive.plist) on a workstation because abc.ca.gov
# blocks GitHub's hosted runners. Each run re-reads the last 6 days, so a missed day is harmless.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

APP_REPO="${APP_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
DATA_REPO="${DATA_REPO:?set DATA_REPO to a git checkout of your archive data repository (kept outside this repo)}"
ENV_FILE="${ABC_ARCHIVE_ENV_FILE:-$HOME/.config/sfhp/abc-archive.env}"   # ABC_ARCHIVE_CONTACT=… (User-Agent contact)

[[ -f "$ENV_FILE" ]] && set -a && source "$ENV_FILE" && set +a
echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) abc-archive start"
git -C "$DATA_REPO" pull -q --rebase --autostash || echo "warning: pull failed; continuing with the local checkout"
cd "$APP_REPO/packages/precedent"
"$APP_REPO/apps/api/.venv/bin/python" -m precedent.abc_archive --repo "$DATA_REPO" --days 6 --weeks 2 --commit --push
echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) abc-archive done"
