# Time-zone pitfalls in dayjs repros

dayjs core uses the host's local time via `Date`. A repro's result therefore
depends on `TZ`, and jest in this repo inherits it from the environment
(`npm test` itself loops over several zones — see `package.json`).

## Default matrix (`scripts/tz-matrix.sh`)

| Zone | Why it is in the set |
|---|---|
| `UTC` | Baseline; no offset, no DST |
| `Asia/Tokyo` | Positive offset, no DST (catches sign errors) |
| `America/New_York` | Negative offset with DST |
| `Europe/London` | Offset 0 in winter but +1 in summer — looks like UTC until it doesn't |
| `Pacific/Auckland` | Large positive offset, southern-hemisphere DST |
| `Asia/Kuala_Lumpur` | Historical offset jump at 1982-01-01 00:00 (+07:30 → +08:00) |
| `America/Sao_Paulo` | Historically had DST transitions *at midnight* (days with no 00:00) |

Add the reporter's zone if it is not here.

## Patterns and what they usually mean

- **Fails only in Kuala_Lumpur/Singapore/Sao_Paulo for old dates:** a
  `startOf`/`endOf`/`daysInMonth` path builds a `Date` at a local wall-clock
  time that does not exist that day, and the engine shifts it. Example:
  `dayjs('1981-12-01').endOf('M')` → `1982-01-01T00:29:59+08:00`, so
  `daysInMonth()` is `1` (issue #3003, related #3137, PR #3175).
- **Off by exactly the UTC offset:** a string without offset was parsed as UTC
  in one path and local in another (`dayjs.utc` vs `dayjs()` vs `dayjs.tz`).
- **Fails only near DST in New_York/London:** `add(n, 'day')` vs
  `add(24, 'hour')` semantics; check what Moment does before calling it a bug.
- **Fails in every zone except UTC:** the test itself (or the reporter) assumed
  UTC — e.g. using `new Date(0)` and asserting the year 1970. This may be a
  *test* bug, not a library bug (see issue #3009).
- **timezone plugin involved (`dayjs.tz`)**: the host TZ still matters, because
  the plugin converts through `Intl` and the local `Date`. Run the matrix anyway.

## Commands

```bash
# Single zone
TZ=Asia/Kuala_Lumpur npx jest test/__repro__/issue-3003.test.js --coverage=false

# Check what the engine does with a wall-clock time directly (no dayjs)
TZ=Asia/Kuala_Lumpur node -e "console.log(new Date(1981,11,31,24,0,0).toString())"

# Offset history of a zone around a date (compare offsets day by day)
TZ=Asia/Kuala_Lumpur node -e "for(let d=29;d<=33;d++)console.log(new Date(1981,11,d).toString())"
```
