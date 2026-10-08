#!/usr/bin/env bash
# trigger-run.sh <id> <prompt>
# Runs <prompt> in a fresh headless Claude Code session from the assignments repo
# (where .claude/skills/dayjs-bug-triage is discovered), saves the stream-json
# transcript to $SCRATCH/trigger/<id>.jsonl, and prints which skills were invoked.
: "${SCRATCH:?set SCRATCH to a scratch directory}"
mkdir -p "$SCRATCH/trigger"
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
out="$SCRATCH/trigger/$1.jsonl"
claude -p "$2" --output-format stream-json --verbose --max-turns 3 \
  --disallowedTools "Edit Write NotebookEdit" > "$out" 2>&1
skills=$(jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use" and .name=="Skill") | .input.skill' "$out" 2>/dev/null | paste -sd, -)
first=$(jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use") | .name' "$out" 2>/dev/null | head -1)
echo "$1 | skill=[${skills}] | first_tool=${first}"
