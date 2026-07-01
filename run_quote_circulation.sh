#!/usr/bin/env bash
# ============================================================
# run_quote_circulation.sh — hands-off Step 3 (quote circulation)
#
# Runs the SerpAPI quote-circulation collector and KEEPS RESUMING
# until every candidate quote has been measured. The collector is
# checkpointed, so each pass only does what's left; on the hourly
# cap it parks and resumes on its own, and this loop is a safety net
# that restarts it if it ever exits with quotes still pending.
#
# Launch it so your Mac never sleeps mid-run:
#     caffeinate -is bash run_quote_circulation.sh
#
# Safe to stop (Ctrl-C) and relaunch — it continues where it left off.
# ============================================================
set -uo pipefail
cd "$(dirname "$0")"

CAND=data/quote_candidates.json
OUT=data/quote_circulation.json

if [[ ! -f "$CAND" ]]; then
  echo "ERROR: $CAND not found. Run Step 1 (32_collect_quote_strings.py) first."
  exit 1
fi

pass=0
while true; do
  pass=$((pass + 1))
  echo "===== pass $pass — $(date '+%H:%M:%S') ====="
  python scripts/33_collect_quote_circulation.py \
      --input "$CAND" --output "$OUT" --anchor off --sleep 0.3 || true

  pending=$(python - "$CAND" "$OUT" <<'PY'
import json, sys
cand = json.load(open(sys.argv[1]))
total = sum(len(r.get("quotes", []) or []) for r in cand)
try:
    out = json.load(open(sys.argv[2]))
    ok = sum(1 for r in out if r.get("status") == "success")
except Exception:
    ok = 0
print(total - ok)
PY
)
  echo ">> quote ancora da misurare: ${pending}"
  if [[ "${pending:-1}" -le 0 ]]; then
    echo ">> COMPLETATO: tutte le quote misurate -> $OUT"
    break
  fi
  echo ">> pausa 60s, poi riprendo automaticamente..."
  sleep 60
done
