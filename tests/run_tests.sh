#!/bin/bash
# Run the repository lint plus every skill's unit tests. No board or GPU needed; tests that need PyYAML skip without it.
#   tests/run_tests.sh
set -u
export PYTHONDONTWRITEBYTECODE=1   # keep __pycache__ out of the skill folders (the lint rejects them)
cd "$(dirname "$0")/.."
rc=0
python3 -m unittest discover -s tests -p 'test_*.py' || rc=1
for d in skills/*/tests; do
  [ -d "$d" ] || continue
  echo "== $d"
  python3 -m unittest discover -s "$d" -p 'test_*.py' || rc=1
done
exit $rc
