# Week 3 Write-up

**Skill name**, and the repo you targeted:
> `dayjs-bug-triage` ([`week3/dayjs-bug-triage/`](dayjs-bug-triage/SKILL.md)), targeting [iamkun/dayjs](https://github.com/iamkun/dayjs) at `dev` commit `436bde0`.
> Claude Code discovers it through a symlink, `.claude/skills/dayjs-bug-triage -> ../../week3/dayjs-bug-triage`.


## Part I: The Workflow

**What the workflow is**, and why it's worth encoding:
> Take a reported dayjs bug (issue number or URL), turn it into a minimal jest repro against the current `src`, run it across a fixed set of time zones, compare with Moment, search for prior issues/PRs, and return one verdict with evidence: CONFIRMED, CONFIRMED-ENV, EXPECTED, USAGE, FIXED-ON-DEV, DUPLICATE-OR-HAS-PR or CANNOT-REPRODUCE.
> It is worth encoding because the dayjs tracker gets a steady stream of reports of mixed quality. Of the 30 most recent open "bug" issues I listed, some are real bugs (#3246), some are locale conventions working as intended (#3142, sv-fi), some only show up in one time zone (#3003), and many already have an open PR (#3048–#3062). The same checklist applies to every one of them, and skipping any step leads to the wrong answer.

**The decision point** in it (what the agent has to judge, not just execute):
> Choosing the verdict. The hard calls are:
> 1. **Is the "expected" value actually expected?** The tie-breaker is Moment parity (or `Intl` for locale strings), not the reporter's opinion. The exception is when Moment is also objectively wrong.
> 2. **Is "passes in UTC" enough to say CANNOT-REPRODUCE?** No. The agent has to judge whether the input is near a historical offset change, DST, or a midnight boundary before giving up.
> 3. **Is reproducing it the end of the work?** If an open PR already targets the root cause, the right output is "go review PR #N", not a competing fix.
> 4. **Is the reporter's root-cause claim right?** It is a lead to verify by reading the code, not a conclusion.

**What you learned running it manually** that you would not have guessed:
> I triaged two issues by hand before writing the skill (in a scratch dayjs clone). The repros I wrote are in `evidence/manual-issue-3246.test.js` and `evidence/manual-issue-3003.test.js`.
> - **#3246** (calendar callback ignores `referenceTime`): it reproduced in UTC, Tokyo and New York, and Moment 2.29.2 behaves correctly, so it is a real bug. But `gh pr list` then showed **PR #3248 already fixes it**. I had expected the hard part to be reproducing it. It was actually knowing when to stop. Most reproducible bugs in this tracker already have a PR.
> - **#3003** (`dayjs('1981-12-01').daysInMonth()` returns 1): **it passes in UTC and Tokyo** and fails only in `Asia/Kuala_Lumpur` and `Asia/Singapore`, where `endOf('M')` yields `1982-01-01T00:29:59+08:00` because the 1982-01-01 +07:30→+08:00 jump removes local midnight. Testing with my own default TZ would have produced a false CANNOT-REPRODUCE. The same root cause sits behind #3137 and PR #3175.
> - Issue repros usually `require('dayjs')`, which is the npm build. Testing that instead of `../../src` cannot distinguish "still broken" from "fixed on dev but not released".
> - Many issues and comments carry AI-assisted "root cause" analyses that look authoritative. They were right in both cases I checked, but the skill still has to verify them rather than copy them.


## Part II: The Skill

**Your description**, verbatim:
```
Reproduce and triage a reported Day.js (dayjs) bug — build a minimal failing jest test against the current src, run it across time zones, compare with Moment, check for duplicate issues/PRs, and return a verdict (confirmed, env-dependent, expected behavior, usage error, fixed on dev, duplicate, cannot reproduce). Use when someone gives a dayjs issue number or URL and asks to reproduce, triage, verify, or confirm it, or asks "is this a dayjs bug?" about surprising dayjs output. Not for reviewing PRs, adding features, or writing general tests.
```

**Why it's worded that way** (what a user would type to trigger it):
> - It names the library both ways ("Day.js (dayjs)"), because users type `dayjs` but docs say Day.js.
> - It lists the verbs people actually use with an issue: *reproduce, triage, verify, confirm*. It also covers the case where there is no issue number, only surprised output ("is this a dayjs bug?").
> - It lists the verdict names, so that a prompt asking "is this expected behavior?" also matches.
> - The final sentence rules out the closest neighbours (PR review, feature work, general test writing). Those also mention dayjs and issues/PRs, and would otherwise steal the trigger.

**Judgment encoded in the body** (what it says to do when things are ambiguous, and what not to do):
> The `Decision rules` section of `SKILL.md`:
> - Passing in UTC is not a reason to give up: try the reporter's TZ and the pitfall zones first.
> - If dayjs matches Moment, the default verdict is EXPECTED, even if the reporter finds the result surprising. The exception is objectively wrong calendar or ISO math.
> - If the bug reproduces only against the npm build, the verdict is FIXED-ON-DEV; find the fixing commit with `git log -S`.
> - A missing plugin, wrong plugin order, or wrong format token is USAGE: show the corrected call.
> - If an open PR already targets the bug, the verdict is DUPLICATE-OR-HAS-PR: report it and do not write a competing fix.
> - Treat the reporter's (or a bot's) root-cause line as a hypothesis to confirm by reading the code.
> - When there is no oracle and the spec is silent, mark the result "needs maintainer decision" instead of picking a side.
>
> The `Do not` list: no fix before a failing repro, no edits to `src/` during triage, no GitHub posting unless asked, don't trust the issue's version number, and don't commit `test/__repro__/`.
>
> The deterministic parts are exact commands (`gh issue view <n> -R iamkun/dayjs --comments`, `gh issue list/pr list --search`, `git log -S`, `TZ=… npx jest … --coverage=false`) or wrapped in scripts.

**Supporting files**, if any, and why they aren't inline:

| File | Contents | Why it's separate |
|---|---|---|
| `references/verdicts.md` | The 7 verdicts with "use when" and the required evidence, precedence rules, and the report template | Needed only at the final step. The table plus template is about as long as the whole SKILL.md body |
| `references/timezone-pitfalls.md` | Why each zone is in the default matrix, failure patterns mapped to likely causes (e.g. the #3003 midnight gap), and raw `TZ=… node -e` probes | Needed only when results differ by TZ or the input is an old date or near DST. Most issues never need it |
| `scripts/new-repro.sh` | Generates `test/__repro__/issue-<n>.test.js` importing `../../src`, plugins and `moment`, with a control test | Gets the deterministic parts right every time (src import, MockDate reset, oracle) without spending tokens on boilerplate |
| `scripts/tz-matrix.sh` | Runs one test file in 7 default zones plus extras and prints a PASS/FAIL table with the first failure's details | The TZ loop is mechanical, and a script gives a consistent table that goes straight into the report |


## Part III: Testing

Method: each prompt was run **3 times** in a **fresh headless session** (`claude -p … --output-format stream-json --max-turns 3`, file-edit tools disallowed), from the assignments repo where the skill is discovered. A run counts as "fired" if the transcript contains a `Skill` tool call with `skill: "dayjs-bug-triage"`. The script is `evidence/trigger-run.sh` and the raw results, one row per run with the prompt text, are in `evidence/trigger-results.tsv`. Per-run turn counts, costs and permission denials, taken from each transcript's `result` event, are in `evidence/run-results.tsv`. The 18 runs cost about $3.08 in total.

**Triggering:**

| Prompt | Should fire? | Did it? |
|---|---|---|
| `dayjs の issue #3239 が再現できるか確認して` ("check whether dayjs issue #3239 reproduces") | Yes | **Yes, 3/3**. `Skill(dayjs-bug-triage)` was the first tool call every time |
| `Can you triage this dayjs issue? https://github.com/iamkun/dayjs/issues/3006` | Yes | **Yes, 3/3**, first tool call |
| `dayjs('1981-12-01').daysInMonth() が 1 を返すんだけど、これって dayjs のバグ？` ("this returns 1, is it a dayjs bug?", with no issue number) | Yes | **Yes, 3/3**, first tool call |
| `dayjs の PR #3248 をレビューして` ("review dayjs PR #3248") | No (near-miss) | **No, 0/3**. Each run went straight to `gh pr view 3248`. One run also `ls`'d the skill folder but did not load it |
| *Extra near-miss:* `dayjs の timezone プラグインで dayjs.tz() と dayjs.utc() の違いと使い分けを教えて` (usage question about the same plugins) | No | **No, 0/3**. Answered directly with no tools |
| *Extra near-miss:* `dayjs の calendar プラグインに、週の始まりを月曜にするオプションを追加したい` (feature request on a plugin that has open bugs) | No | **No, 0/3**. Explored the code with Bash |

I also tried the same prompts through Agent-tool subagents and **discarded those results**. The skill was created mid-session, so the subagent's skill registry did not contain it: on the positive prompt the subagent found the folder by path and read `SKILL.md` by hand. On the near-miss prompt it correctly picked a different skill (`code-review`). Headless `claude -p` gives a fresh session with normal discovery, so it is the valid test.

**End-to-end run** on your repo, and the result:

Fresh `claude -p` session, prompt: `dayjs の issue #3239 が再現できるか確認して。dayjs のチェックアウトは <scratch>/dayjs にあります（npm ci 済み）。` ("check whether dayjs issue #3239 reproduces; the checkout is at <scratch>/dayjs, npm ci done"). #3239 was not one of the issues I triaged by hand. Permissions were limited to read-only `gh`, `git log/show`, `jest`, `node`, the skill scripts, and writes inside the clone, so posting to GitHub was impossible. The run took 35 turns and cost $0.67 (`evidence/run-results.tsv`). Full tool sequence: `evidence/e2e-3239-tool-calls.txt`. Full report: `evidence/e2e-3239-report.md`. Repro it wrote: `evidence/issue-3239.test.js`.

```
Tool sequence (abridged):
  Skill(dayjs-bug-triage) → gh issue view 3239 --comments → git log -1 (record sha)
  → Read new-repro.sh / tz-matrix.sh / verdicts.md → Write test/__repro__/issue-3239.test.js
  → gh issue list / gh pr list --search "customParseFormat week utc"
  → TZ=<zone> npx jest … in 7 zones → gh pr view 3240 / gh pr diff 3240

Report (translated from Japanese; original in evidence/e2e-3239-report.md):
  ## Triage: iamkun/dayjs#3239 — customParseFormat week token (w/ww) ignored with dayjs.utc()
  Verdict: reproduced, but DUPLICATE-OR-HAS-PR (open fix PR #3240)
  Tested at: dayjs 436bde0 (dev), Node v24.21.0, Moment 2.29.2

  | TZ                 | utc (claim) | local (control) | dayjs.utc             | moment.utc            |
  | UTC                | ✕           | ✓               | 2024-01-01T00:00:00Z  | 2024-07-28T00:00:00Z  |
  | Asia/Tokyo … America/Sao_Paulo (6 more) | ✕ | ✓  | same                  | same                  |
  → fails in all 7 zones: a logic bug, not TZ-dependent.

  Root cause: the reporter's analysis holds. In src/plugin/customParseFormat/index.js:202-204,
  the `if (utc)` branch returns before the parsed `week` is applied; week handling
  (207-209) exists only on the local branch.
  Side findings: the reporter's snippet also needs advancedFormat to *format* 'ww';
  in local mode dayjs lands on Monday 07-29 vs Moment's Sunday 07-28 (same week 31), a separate question.
  Prior work: PR #3240 (open, mergeable) fixes the same root cause. #2632/#2709/#2827 are related but different (ISO week parsing).
  Next step: wait for PR #3240 review and merge. src/ was not edited during triage.
```

I checked the result myself: `git status` in the clone shows only `?? test/__repro__/`, so `src/` was untouched. Lines 202–209 of `customParseFormat/index.js` match the root-cause description, and PR #3240 exists ("fix(customParseFormat): apply the week token when parsing in UTC mode", OPEN). The run followed the decision rules: it reproduced against `src`, used Moment as the oracle, ran all 7 zones before concluding the bug is not TZ-dependent, found the existing PR, and stopped instead of writing a competing fix.

One rough edge: 7 permission denials. All of them came from my test harness's narrow allowlist (`cd … &&` compound commands, `bash <script>` invocations, and the `.claude/skills/…` symlink path not matching the allowlisted `week3/…` path), not from the skill. When `tz-matrix.sh` was denied, the agent fell back to the equivalent per-zone `npx jest` loop and still produced the full table. Two deviations from the skill's procedure came out of this. The agent read `new-repro.sh` and wrote the test file by hand instead of running the script. And the extra zone it tried to add (`Europe/Is…`, line 21 of the tool-call log) was dropped in the fallback loop, so only the 7 default zones were run.


## Submission
1. `Command (⌘) + F` for the to-do placeholder. No results means you're done.
2. Confirm the skill directory itself is committed under `week3/`.
3. Push all changes to your remote repository and submit via Gradescope.
