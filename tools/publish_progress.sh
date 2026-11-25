#!/usr/bin/env bash
# Regenerate the public progress data, validate it, commit and push to main.
# Run after finishing a task, changing its status, finding a bug or checking a milestone.
# Usage: tools/publish_progress.sh [--no-push] [--no-wait]
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
if [ -e "$REPO/.publish.lock" ]; then echo "publish_progress: locked (.publish.lock exists), refusing to run" >&2; exit 4; fi
PUSH=1; WAIT=1
for a in "$@"; do case "$a" in --no-push) PUSH=0;; --no-wait) WAIT=0;; esac; done

python3 tools/sync_progress.py            # exit 2 = private data found, 1 = broken sources
python3 scripts/validate.py
python3 scripts/scan_private.py
python3 scripts/build.py >/dev/null   # build must succeed too

git add data/progress.json data/overrides.json
if git diff --cached --quiet; then
  echo "publish_progress: nothing changed, data is up to date"
else
  UPD="$(python3 -c "import json;print(json.load(open('data/progress.json'))['updated'])")"
  git commit -q -m "data: progress update ${UPD}

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  echo "publish_progress: committed"
fi

if [ "$PUSH" = 1 ]; then
  git push -q origin main
  echo "publish_progress: pushed to main"
  if [ "$WAIT" = 1 ] && command -v gh >/dev/null 2>&1; then
    sleep 5
    RUN="$(gh run list --workflow deploy.yml --branch main --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null || true)"
    if [ -n "$RUN" ]; then
      gh run watch "$RUN" --exit-status >/dev/null && echo "publish_progress: workflow OK (run $RUN)" \
        || { echo "publish_progress: WORKFLOW FAILED (run $RUN), see: gh run view $RUN --log-failed" >&2; exit 1; }
    fi
  fi
fi
