# Verdicts

Pick exactly one. If two seem to apply, use the first one in this table that fits.

| Verdict | Use when | Evidence required |
|---|---|---|
| DUPLICATE-OR-HAS-PR | An open/closed issue or open PR already covers the same root cause | Link(s); one line on why it is the same root cause, not just the same symptom |
| FIXED-ON-DEV | Reproduces with the published npm version but not with `src` at the current commit | Both results; the fixing commit if found |
| USAGE | Behavior is correct once the call is fixed (plugin not extended, `dayjs.utc` vs `dayjs.tz`, wrong format token, strict-mode parsing not enabled) | The corrected call and its passing output |
| EXPECTED | dayjs matches Moment / Intl / ISO 8601, or the documented behavior | Oracle output side by side with dayjs output |
| CONFIRMED-ENV | Fails only in some time zones, locales, or Node versions | TZ matrix table showing pass and fail rows |
| CONFIRMED | Fails in every tested environment, and the oracle disagrees with dayjs | Failing test output + oracle output |
| CANNOT-REPRODUCE | Passes everywhere tried, including the reporter's stated environment | The TZ list tried, and the specific missing information to ask the reporter for |

Notes:
- DUPLICATE wins over CONFIRMED because the actionable outcome is "go to that
  thread", but still state whether you reproduced it.
- If the issue bundles several claims, give a verdict per claim.

## Report template

```markdown
## Triage: iamkun/dayjs#<n> — <issue title>

**Verdict:** <VERDICT> <(needs maintainer decision) if applicable>
**Tested at:** dayjs `<short sha>` (dev), Node <version>

### Reproduction
`test/__repro__/issue-<n>.test.js` — <one sentence on what it asserts>

| TZ | Result | Observed |
|---|---|---|
| UTC | ✓/✕ | ... |

### Oracle
Moment <version>: <result>. <Intl/ISO note if relevant>

### Root cause
<file:line and the mechanism, verified by reading the code — or "not
investigated" if the verdict made it unnecessary. Say whether the reporter's
claimed cause held up.>

### Prior work
<related issues/PRs, or "none found for: <search terms>">

### Suggested next step
<one line: e.g. review PR #x, ask reporter for TZ, close as expected, write fix>
```
