#!/usr/bin/env bash
# run-task.sh <id> <prompt>
# Runs <prompt> in a fresh headless Claude Code session inside the dayjs fork
# (where CLAUDE.md is picked up), saves the stream-json transcript to
# $SCRATCH/<id>.jsonl, and writes the tool-call sequence and final report
# next to this script. Commits, pushes and gh are blocked.
: "${SCRATCH:?set SCRATCH to a scratch directory}"
DAYJS="${DAYJS:-$HOME/lectures/dayjs}"
here="$(cd "$(dirname "$0")" && pwd)"
out="$SCRATCH/$1.jsonl"
cd "$DAYJS"
claude -p "$2" --output-format stream-json --verbose --max-turns 60 \
  --permission-mode acceptEdits \
  --allowedTools "Bash(npm *) Bash(npx *) Bash(node *) Bash(git status*) Bash(git diff*) Bash(git log*) Bash(ls *) Bash(cat *) Bash(grep *) Bash(TZ=*) Read Edit Write Glob Grep" \
  --disallowedTools "Bash(git commit*) Bash(git push*) Bash(gh *)" > "$out" 2>&1
jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use")
  | .name + ": " + ((.input.command // .input.file_path // .input.pattern // "") | gsub("\n"; " ") | .[0:160])' \
  "$out" > "$here/$1-tool-calls.txt"
jq -r 'select(.type=="result") | .result' "$out" > "$here/$1-report.md"
jq -r 'select(.type=="result") | "\(.num_turns) turns, $\(.total_cost_usd), \(.duration_ms/1000|floor)s"' "$out"
