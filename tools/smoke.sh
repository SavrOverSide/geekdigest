#!/usr/bin/env bash
# Runs every bot's scenarios through the real aiogram in a throwaway container (fake network, empty data).
# Usage on the server: bash /opt/tenge/geekdigest/tools/smoke.sh
set -u
fail=0
for b in wordlore ideaforgegen geekdigest; do
  echo "=== $b"
  docker run --rm -i -v /opt/tenge/$b/tests:/app/tests:ro $b sh -c "rm -rf /app/data/* && python -" \
    < /opt/tenge/$b/tests/real_smoke.py 2>&1 | tail -4 || fail=1
done
exit $fail
