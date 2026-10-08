---
name: dayjs-bug-triage
description: Reproduce and triage a reported Day.js (dayjs) bug — build a minimal failing jest test against the current src, run it across time zones, compare with Moment, check for duplicate issues/PRs, and return a verdict (confirmed, env-dependent, expected behavior, usage error, fixed on dev, duplicate, cannot reproduce). Use when someone gives a dayjs issue number or URL and asks to reproduce, triage, verify, or confirm it, or asks "is this a dayjs bug?" about surprising dayjs output. Not for reviewing PRs, adding features, or writing general tests.
---

# Day.js bug triage

Goal: a **verdict with evidence**, not a fix. The deliverable is a failing (or
deliberately passing) repro test plus a short report. Fixing is a separate task
the user can ask for afterwards.

## Procedure

`scripts/` and `references/` live in this skill's base directory; run the
scripts by absolute path with the dayjs repo root as the working directory.

1. **Locate the repo.** Find a dayjs checkout (`package.json` `"name": "dayjs"`).
   If none, `git clone https://github.com/iamkun/dayjs.git && cd dayjs && npm ci`.
   Record `git log -1 --format='%h %s'` — every verdict is relative to this commit.
2. **Read the issue in full**, comments included:
   `gh issue view <n> -R iamkun/dayjs --comments`.
   Extract: claimed input, expected, actual, dayjs version, TZ, plugins, locale.
   If the expected value is not stated, derive it from Moment (step 5), never
   from the reporter's wording alone.
3. **Write the repro test** with `scripts/new-repro.sh <n>` (creates
   `test/__repro__/issue-<n>.test.js`). Import from `../../src`, not `dayjs` —
   the npm build may be older than `dev`. Freeze the clock with `MockDate` if
   "now" is involved. One `it` for the claim, one control `it` showing the
   surrounding behavior that *does* work. Keep it under ~30 lines.
4. **Run across time zones:** `scripts/tz-matrix.sh test/__repro__/issue-<n>.test.js [extra TZs]`.
   Always add any TZ the reporter names. Read
   [references/timezone-pitfalls.md](references/timezone-pitfalls.md) whenever
   the result differs by TZ or the input is a pre-1990 date, near DST, or a
   midnight/month boundary.
5. **Consult the oracle.** dayjs aims for Moment parity, and `moment` is a
   devDependency: run the same operation with `moment` in the same test.
   For locale strings also check `Intl.DateTimeFormat`.
6. **Search for prior work** before saying anything is new:
   `gh issue list -R iamkun/dayjs --state all --search "<keywords>"` and
   `gh pr list -R iamkun/dayjs --state all --search "<keywords>"`.
   Search by the affected function/plugin name, not the reporter's title.
7. **Decide the verdict** using [references/verdicts.md](references/verdicts.md)
   and write the report in its template.

## Decision rules (where judgment is needed)

- **Passes in UTC ≠ not a bug.** Many dayjs bugs only appear in zones with
  historical offset changes (e.g. `Asia/Kuala_Lumpur` 1981-12-31). Never return
  CANNOT-REPRODUCE until the reporter's TZ and the pitfall zones were tried.
- **Matches Moment ⇒ default to EXPECTED**, even if the reporter finds it
  surprising. Say so plainly and point to the Moment result. Exception: if Moment
  is *also* wrong by an objective standard (calendar math, ISO 8601), call it
  CONFIRMED and note that Moment shares it.
- **Reproduces only via the npm build** ⇒ FIXED-ON-DEV; find the fixing commit
  with `git log -S '<code fragment>' --oneline -- src/`.
- **Plugin not extended / wrong plugin order / wrong format token** ⇒ USAGE.
  Show the corrected call working.
- **An open PR already targets it** ⇒ DUPLICATE-OR-HAS-PR. Report the PR number
  and whether your repro passes with the PR's change if it is trivial to check;
  do not write a competing fix.
- **Reporter's analysis is just a hypothesis.** Issues (and bot-assisted
  comments) often name a "root cause" line. Treat it as a lead, confirm it by
  reading the code path yourself, and say whether it held up.
- **Ambiguous expected value** (no Moment counterpart, spec silent): report
  CONFIRMED-behaviour-as-described but mark "needs maintainer decision" rather
  than picking a side.

## Do not

- Propose or apply a fix before the repro test fails for the reported reason.
- Edit anything under `src/` during triage.
- Post comments, labels, or PRs to GitHub unless the user explicitly asks.
- Trust the issue's version number — verify against the current commit.
- Leave the repro file in a commit; `test/__repro__/` is scratch space.
