# CLAUDE.md

Day.js: a ~2 KB immutable date library with a Moment.js-compatible API. The core stays tiny; everything else is an opt-in plugin or locale. Bundle size and Moment parity are the two constraints behind most design decisions.

## Layout

- `src/index.js`: the core (the `Dayjs` class and the `dayjs()` factory). `src/constant.js` holds unit names and regexes, `src/utils.js` holds helpers.
- `src/plugin/<name>/index.js`: 37 plugins. `src/locale/<code>.js`: 143 locales.
- `types/`: hand-written `.d.ts`, one per plugin and locale. Nothing type-checks them, but `test/plugin/declarations.test.js` fails if a plugin has no `types/plugin/<name>.d.ts`.
- `test/` mirrors `src/`: `test/<area>.test.js`, `test/plugin/<name>.test.js`, `test/locale/<code>.test.js`, plus `test/issues/issue<N>.*.test.js` for regressions.

## Commands

```sh
npm ci
TZ=UTC npm test                                     # full suite, the way CI runs it
TZ=UTC npx jest test/plugin/utc.test.js --coverage=false   # one file
npm run lint                                        # ESLint over src/ test/ build/
npm run build                                       # rollup to dayjs.min.js, plugin/, locale/, then the size check
```

- Always set `TZ`. Plain `npm test` ends with a full jest run in the **host** TZ, and outside UTC some `dayOfYear`, `localizedFormat` and `timezone` tests fail even on a clean checkout. CI is ubuntu/UTC. Before calling a failure yours, rerun it with `TZ=UTC` on the unmodified file.
- `npm test` enforces **100% line coverage** over `src/`. Every new branch needs a test, or the suite fails even when every assertion passes.
- On Node ≥17 the size step of `npm run build` fails with `ERR_OSSL_EVP_UNSUPPORTED`. Use `NODE_OPTIONS=--openssl-legacy-provider npm run size`. The bundle limit is 2.99 KB gzipped (about 2.79 KB today), so think twice before adding code to `src/index.js`. It probably belongs in a plugin.

## Conventions

- Style: ESLint `airbnb-base`, **no semicolons, no trailing commas**. Import paths have no `.js` extension.
- Plugins: `export default (option, DayjsClass, dayjsFactory) => { const proto = DayjsClass.prototype ... }`. To extend an existing method, save it as `const oldX = proto.x` and call `oldX.bind(this)(...)`. Never import `src/index` or `src/utils` from a plugin: import only `../../constant`, and reach helpers through `this.$utils()`.
- A new plugin is three files: `src/plugin/<name>/index.js`, `types/plugin/<name>.d.ts` (augment `interface Dayjs` in `declare module 'dayjs'`), and `test/plugin/<name>.test.js`.
- Locales: the first line must be `// <English name> [<code>]`, because `build/index.js` and `test/locale/keys.test.js` both parse it. `name` must equal the lowercase filename. Locales `import dayjs from 'dayjs'`; jest maps that to `src/` via `test/__mocks__/dayjs.js`.
- Tests import from `../../src`, not `dayjs`. Use Moment as the oracle where the API overlaps: `expect(dayjs(x).format()).toBe(moment(x).format())`. Pin "now" with `MockDate.set(...)` in `beforeEach` and `MockDate.reset()` in `afterEach`.
- Instance state lives in `$` fields (`$d` Date, `$L` locale, `$u` UTC flag, `$x` plugin extras). Keep instances immutable: setters go through `clone()`.

## Guardrails

- Don't edit build output at the repo root: `dayjs.min.js`, `plugin/`, `locale/`, `esm/`, `index.d.ts`, `locale.json`. These are gitignored copies. Tests never read them, so a fix there silently does nothing. Edit `src/` or `types/`.
- Don't edit `CHANGELOG.md` (semantic-release writes it) or `patches/` (used only by the release workflow).
- `docs/<lang>/` is translated README copy, not API documentation. The real docs live in a separate repo (day.js.org).
- PRs target `dev`; `master` is release-only. Commit messages are Conventional Commits (`fix(plugin): ...`, `feat: ...`) because semantic-release derives versions from them.
