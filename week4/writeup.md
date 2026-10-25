# Week 4 Write-up

**Repo chosen** and link to your fork:
> [iamkun/dayjs](https://github.com/iamkun/dayjs), forked to [otakumesi/dayjs](https://github.com/otakumesi/dayjs) (branch `dev`, base commit `436bde0`; the file was added in [`6b0c851`](https://github.com/otakumesi/dayjs/blob/dev/CLAUDE.md)). The demo `isWeekend` plugin from Part III was deleted afterwards and survives only as [`evidence/task2-isweekend-plugin.diff`](evidence/task2-isweekend-plugin.diff).

**File you wrote** (`AGENTS.md` or `CLAUDE.md`):
> `CLAUDE.md` at the root of the fork, copied here as [`week4/CLAUDE.md`](CLAUDE.md) (40 lines, about 520 words).


## Part I: Exploration

| | Finding |
|---|---|
| Build / run | `npm ci`, then `npm run build`: rollup (`build/index.js`) emits one UMD bundle per locale and plugin plus `dayjs.min.js`, copies `types/` to the repo root, then runs `npm run size`. On Node ≥17 the size step dies with `ERR_OSSL_EVP_UNSUPPORTED` (old webpack inside `size-limit`). `NODE_OPTIONS=--openssl-legacy-provider npm run size` passes (2.79 KB, limit 2.99 KB). `npm run babel` builds `esm/` and is used only in the release workflow. There is nothing to "run": it is a library. |
| Test | `npm test` runs `test/timezone.test` under 4 TZs and `test/plugin/timezone.test` under 4 more, then the full jest suite with a **100% line-coverage threshold**. That final run uses the host TZ. On my machine (America/Los_Angeles) 6 tests fail in `dayOfYear`, `localizedFormat` and `timezone`. `TZ=UTC npm test` passes 794/794, which matches CI (ubuntu, UTC). A single file: `TZ=UTC npx jest test/plugin/utc.test.js`. |
| Lint / format | `npm run lint` (ESLint `airbnb-base` + no semicolons + no trailing commas, over `src/* test/* build/*`; also a `pre-commit` hook). Prettier only touches `docs/**/*.md`. |
| Key directories and entry points | `src/index.js` is the core (the `Dayjs` class and the `dayjs()` factory). `src/constant.js` and `src/utils.js` hold the unit constants and helpers. `src/plugin/<name>/index.js` has 37 plugins, `src/locale/<code>.js` has 143 locales, and `types/` holds hand-written `.d.ts` (one per plugin and locale). Tests mirror this: `test/*.test.js`, `test/plugin/<name>.test.js`, `test/locale/<code>.test.js`, and `test/issues/issueNNNN.*.test.js` for regressions. |
| Unstated conventions | Plugins are `export default (option, DayjsClass, dayjsFactory) => {}` and patch `DayjsClass.prototype`. They wrap an existing method by saving `const oldX = proto.x` and calling it, and they never import `src/index` or `src/utils`. They import only `../../constant` and reach helpers via `this.$utils()` (12 plugins do). Locales `import dayjs from 'dayjs'` (external in rollup, mapped to `src/` in jest by `test/__mocks__/dayjs.js`) and must start with a `// Name [code]` comment: `build/index.js` and `test/locale/keys.test.js` both parse it. Instance state lives in `$`-prefixed fields (`$d`, `$L`, `$u`, `$x`). About half the tests assert against Moment as the oracle (`expect(dayjs(x).f()).toBe(moment(x).f())`), and time-dependent tests pin the clock with `MockDate.set` / `MockDate.reset`. A new plugin is three files: src, `types/plugin/<name>.d.ts`, and its test. Commits are Conventional Commits (`fix(plugin): ...`) because semantic-release reads them. PRs target `dev`; `master` is release-only. |
| Off-limits (generated, vendored) | Build output at the repo root: `dayjs.min.js`, `/plugin`, `/locale`, `/esm`, `/index.d.ts` and `locale.json` (gitignored, so edits there silently vanish and never reach tests, which import `src/`). `CHANGELOG.md` is written by semantic-release. `patches/` is a `patch-package` patch for `@semantic-release/github`, applied only in `release.yml`. `docs/<lang>/` holds translated READMEs, not API docs used by the code. |

**How you figured it out**: what you asked the agent, what you had to read yourself:
> I had Claude Code fork and clone the repo, run `npm ci`, and then **run** every script in `package.json` rather than read them. Running them is what surfaced the two traps: `npm test` failing on a Pacific-time laptop while CI is green, and `npm run build` dying in the size check on Node 24. Neither appears in the README or CONTRIBUTING. After that it read `build/index.js` (the copy of `types/` to the root and the locale-comment regex), `.eslintrc.json`, `test/__mocks__/dayjs.js`, one small plugin with its test and `.d.ts`, `test/locale/keys.test.js`, the workflows, and `git log` for commit style. I checked the TZ explanation myself: the same suite passes 794/794 under `TZ=UTC` and fails 2 tests under `TZ=America/New_York`, so the failures follow the host TZ, not the code.


## Part II: The File

**Anything you deliberately left out**, and why:
> - **README material**: the API, install instructions, the plugin list. The agent can read `src/plugin/` itself, and the file loads into every context.
> - **Generic advice**: "write tests", "keep functions small", "search issues before filing". A competent model already does all of this, so none of it is specific to this repo.
> - **The bug-triage procedure** from my Week 3 skill (run the repro across 7 TZs, compare with Moment, check for duplicate PRs). Only triage needs it, so it stays in the skill, which loads on demand. I kept just the one fact every task needs: run tests with `TZ=UTC`, and rerun a failure on the unmodified file before blaming your change.
> - **Browser tests** (`karma.sauce.conf.js`, `npm run test:sauce`). They need Sauce Labs credentials, CI doesn't run them, and an agent can't run them locally.
> - **`npm run babel` / `esm/`**: only the release workflow uses it. All an agent needs to know is that `esm/` is generated, and the guardrail already says so.

**The hardest call** on what to include:
> The internals line (`$d`, `$L`, `$u`, `$x`, immutability through `clone()`). It reads like architecture trivia, and a model could rediscover it by opening `src/index.js`. I kept it because plugin work touches these fields constantly, and the plausible mistake, mutating `this.$d` inside a setter, breaks immutability without failing any obvious test. I went the other way on the Moment-oracle test idiom versus a full testing section: one line with a copy-pasteable `expect(...).toBe(moment(...)...)` shape carries the convention, so I didn't explain *why* Moment is the oracle.


## Part III: Trying It Out

| # | Task | Did the agent use your commands and conventions? |
|---|---|---|
Each task ran in a fresh headless `claude -p` session inside the fork, started by [`evidence/run-task.sh`](evidence/run-task.sh). Edits were auto-accepted, and `git commit`, `git push` and `gh` were blocked. The host TZ was America/Los_Angeles, the setting where a plain `npm test` fails. The prompts were in Japanese and never mentioned time zones. Per-run numbers are in [`evidence/run-results.tsv`](evidence/run-results.tsv).

| # | Task | Did the agent use your commands and conventions? |
|---|---|---|
| 1 | "Run the whole test suite and tell me the result." ([tool calls](evidence/task1-test-suite-tool-calls.txt), [report](evidence/task1-test-suite-report.md)) | **Yes.** Its first command was `TZ=UTC npm test`, straight from the file, and it reported 794/794 passing and the 100% line threshold met. That took 4 turns and 33 s. **Control without `CLAUDE.md`** (same prompt, [tool calls](evidence/task1-baseline-no-claudemd-tool-calls.txt), [report](evidence/task1-baseline-no-claudemd-report.md)): it ran plain `npm test`, hit the 6 host-TZ failures, rediscovered the cause on its own by rerunning with `TZ=UTC`, and then offered to "fix" the tests or `package.json`, a change CI doesn't need. That took 6 turns and 52 s. The model can work out the TZ trap without help. What the file buys is skipping the detour and not proposing the bogus fix. One small error in the run with the file: it said the bare `test-tz` step ran in the "host TZ", but under `TZ=UTC` that step also runs in UTC. |
| 2 | "Add an `isWeekend` plugin so `dayjs().isWeekend()` returns true on Saturday and Sunday." ([tool calls](evidence/task2-isweekend-plugin-tool-calls.txt), [report](evidence/task2-isweekend-plugin-report.md), [diff](evidence/task2-isweekend-plugin.diff)) | **Mostly yes.** It wrote exactly the three files the file lists (src, `types/plugin/isWeekend.d.ts`, test) and used the `(o, c)` prototype-patch shape. It had also read `isToday` as a model, so that part isn't purely the file's doing. It pinned "now" with `MockDate`, wrote no semicolons, ran tests with `TZ=UTC`, and explicitly included `test/plugin/declarations.test.js` in its first run, which comes directly from the line I added after fact-checking. It ran `npx eslint` on the new files, checked a second TZ (`Asia/Tokyo`), and offered a Conventional Commit message (`feat(plugin): add isWeekend plugin`) instead of committing. **Gap:** its full-suite check was `TZ=UTC npx jest`, not `TZ=UTC npm test`. The 100% coverage threshold is passed only on the `npm test` command line, so its "line coverage is 100%" was read off the report, not enforced. I reran `TZ=UTC npm test` and `npm run lint` myself, and both pass. |

**One thing you'd change** about the file after watching it get used:
> Add an explicit "done means" line: *before reporting a change as finished, run `TZ=UTC npm test` (not `npx jest`; only `npm test` enforces the 100% coverage threshold and the per-TZ runs) and `npm run lint`*. In task 2 the agent used my single-file command for the full suite, because the file presents `npx jest` as the way to run tests and leaves the threshold as a property of the suite rather than of a specific command. The plugin happened to be fully covered, but an uncovered branch would have been reported as green.


## Submission
1. `Command (⌘) + F` for `TODO`. No results means you're done.
2. Push all changes to your remote repository and submit via Gradescope.
