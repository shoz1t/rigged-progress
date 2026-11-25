#!/usr/bin/env bash
# Exit 0 if data/progress.json matches the project sources, 3 if it is behind.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 tools/sync_progress.py --check
rc=$?
[ $rc = 3 ] && echo "progress drift: run tools/publish_progress.sh" >&2
exit $rc
