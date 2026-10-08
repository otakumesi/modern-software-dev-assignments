#!/usr/bin/env bash
# Usage: new-repro.sh <issue-number> [plugin-name ...]
# Run from the dayjs repo root. Creates test/__repro__/issue-<n>.test.js
# importing dayjs from ../../src (not the npm build) plus moment as the oracle.
set -euo pipefail

n="${1:?usage: new-repro.sh <issue-number> [plugin ...]}"
shift || true
n="${n##*/}"; n="${n#\#}"   # accept "#3239" or an issue URL
case "$n" in ''|*[!0-9]*) echo "error: issue number must be numeric" >&2; exit 1;; esac

grep -q '"name": "dayjs"' package.json 2>/dev/null || { echo "error: run from the dayjs repo root" >&2; exit 1; }

out="test/__repro__/issue-${n}.test.js"
mkdir -p test/__repro__
[ -e "$out" ] && { echo "exists: $out (not overwritten)"; exit 0; }

{
  echo "import MockDate from 'mockdate'"
  echo "import moment from 'moment'"
  echo "import dayjs from '../../src'"
  for p in "$@"; do echo "import ${p} from '../../src/plugin/${p}'"; done
  echo
  for p in "$@"; do echo "dayjs.extend(${p})"; done
  cat <<EOF

// Triage repro for https://github.com/iamkun/dayjs/issues/${n}
// Run: TZ=<zone> npx jest ${out} --coverage=false

afterEach(() => MockDate.reset())

it('#${n} reported behavior', () => {
  // MockDate.set('2026-01-01T12:00:00Z') // freeze "now" if the issue involves it
  const actual = dayjs() // TODO: reporter's input
  const oracle = moment() // same operation in Moment
  console.log(process.env.TZ, 'dayjs:', actual.format(), 'moment:', oracle.format())
  expect(actual.format()).toBe(oracle.format()) // TODO: expected value
})

it('#${n} control: nearby behavior that works', () => {
  // TODO: a neighbouring input that should pass, to show the failure is specific
})
EOF
} > "$out"

echo "created: $out"
