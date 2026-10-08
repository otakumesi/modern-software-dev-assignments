#!/usr/bin/env bash
# Usage: tz-matrix.sh <test-file> [extra TZ ...]
# Run from the dayjs repo root. Runs one jest file in each time zone and prints
# a pass/fail table, followed by the failure details of the first failing zone.
set -uo pipefail

file="${1:?usage: tz-matrix.sh <test-file> [extra TZ ...]}"
shift
grep -q '"name": "dayjs"' package.json 2>/dev/null || { echo "error: run from the dayjs repo root" >&2; exit 1; }
[ -f "$file" ] || { echo "error: no such file: $file" >&2; exit 1; }
zones=(UTC Asia/Tokyo America/New_York Europe/London Pacific/Auckland Asia/Kuala_Lumpur America/Sao_Paulo "$@")

first_fail=""
printf '%-22s %-6s %s\n' TZ RESULT TESTS
for tz in "${zones[@]}"; do
  log="$(TZ="$tz" npx jest "$file" --coverage=false 2>&1)"
  if [ $? -eq 0 ]; then res=PASS; else res=FAIL; [ -z "$first_fail" ] && first_fail="$tz" && fail_log="$log"; fi
  printf '%-22s %-6s %s\n' "$tz" "$res" "$(grep -E '^Tests:' <<<"$log" | sed 's/^Tests: *//')"
done

if [ -n "$first_fail" ]; then
  echo
  echo "--- first failure ($first_fail) ---"
  grep -vE '^\s*at ' <<<"$fail_log" | sed -n '/●/,$p' | head -40
fi
