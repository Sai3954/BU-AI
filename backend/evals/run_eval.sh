#!/usr/bin/env bash
# Run the fixed 100-question evaluation against a TEST copy of the API (EVAL_MODE=true).
# The token is typed at a hidden prompt: it is never stored in this file, the address, shell history or GitHub.
#
#   bash run_eval.sh https://your-test-service.onrender.com before
#   bash run_eval.sh https://your-test-service.onrender.com after
#
# Writes eval-<label>.jsonl (one line per part of 10 questions) in the current folder. Send that file to Claude.
set -euo pipefail
BASE="${1:?usage: bash run_eval.sh <test service address> <label, e.g. before or after>}"
LABEL="${2:?give a label, e.g. before or after}"
BASE="${BASE%/}"
OUT="eval-${LABEL}.jsonl"

read -rsp "Evaluation token (input hidden): " EVAL_TOKEN; echo
HDR="$(mktemp)"; chmod 600 "$HDR"
trap 'rm -f "$HDR"' EXIT
printf 'X-Eval-Token: %s\n' "$EVAL_TOKEN" > "$HDR"
unset EVAL_TOKEN

curl -fsS "$BASE/api/health" > /dev/null || { echo "The test service is not answering at $BASE/api/health"; exit 1; }
: > "$OUT"
for part in 1 2 3 4 5 6 7 8 9 10; do
  printf 'Part %s of 10... ' "$part"
  for try in 1 2 3; do
    code=$(curl -sS -o part.tmp -w '%{http_code}' --max-time 900 -H @"$HDR" "$BASE/api/eval/run?part=$part")
    [ "$code" = "429" ] || break
    printf '(rate limit, waiting 65 s) '; sleep 65
  done
  if [ "$code" != "200" ]; then
    echo "failed (HTTP $code). 401 = wrong token, 404 = EVAL_MODE/EVAL_TOKEN not set, 429 = wait a minute."
    rm -f part.tmp; exit 1
  fi
  tr -d '\n' < part.tmp >> "$OUT"; echo >> "$OUT"; rm -f part.tmp
  echo "done"
  sleep 20   # stays well under the per-minute limit
done
echo "Finished: $OUT ($(wc -l < "$OUT" | tr -d ' ') parts). Send this file to Claude."
