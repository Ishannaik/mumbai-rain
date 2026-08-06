# Recent-Rain Skew Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the train/serve skew where the collector logs `recent_rain_mm` as *yesterday 21:00–23:00* while the browser serves a *rolling last-3h* value, then backfill the historical column and retrain so the live model is trained and served on the same feature — bundled with three safe honesty/resilience fixes that can ship first.

**Architecture:** `pipeline/sources.py` owns all Open-Meteo I/O. We refactor the recent-rain window into a **pure** function `recent_rain_from_series(times, precip, now_stamp)` that mirrors the browser's `shapeForecast()` in `src/layouts/Almanac.astro` (sum the 3 hours strictly *before* the current hour). A one-shot `pipeline/backfill_recent_rain.py` re-derives the historical column from one Open-Meteo `past_days` fetch and rewrites `data/log.csv`, after which `pipeline/train.py` promotes a corrected model. Three cheap wins (honest "measured now" label, HTTP retry/backoff, a scoreboard freshness line) are sequenced first so the user can stop early.

**Tech Stack:** Astro 7 static site (zero-JS home + one inline JS island), Python 3.11 pipeline (`requests`, `scikit-learn`) run via `uv`, JS unit tests via `bun test`, GitHub Actions cron (collect hourly, retrain daily), Vercel static hosting.

## Global Constraints

- **START FROM `origin/main`, NOT the local checkout.** The local working tree is ~59 commits / ~7 days STALE. Branching off local `main` and rewriting `data/log.csv` would CLOBBER a week of the bot's committed snapshots. Task 1 is a mandatory pre-flight; every file/line reference below was verified against `origin/main` via `git show origin/main:<path>`.
- **`data/log.csv` is the bot's live database.** Only Task 8 may rewrite it, and only from a branch started at `origin/main`.
- **Feature/serving parity is sacred.** Feature order MUST stay `[fc_bestmatch_mm, fc_ecmwf_mm, hour_sin, hour_cos, recent_rain_mm]` in all three places: `pipeline/train.py` `FEATURE_NAMES`, `pipeline/train.py` `row_to_features`, and `src/lib/nowcast.js` `rowFeatures`. This plan does not reorder or rename features.
- **`public/model.json` schema is stable.** Keys: `type, features, weights, intercept, trained_at, n_train, n_test, brier, raw_brier, clim_brier, champion_brier`. Do not add/remove keys; `train.py` owns writes to it.
- **$0 / keyless only.** Open-Meteo (keyless) and METAR/NOAA (keyless) only. **No new dependencies** — `urllib3` and `requests.adapters` used in Task 3 already ship transitively with `requests` (a current direct dependency); do not edit `pyproject.toml`.
- **Do not break `uv run pytest -q`.** `retrain.yml` gates promotion on it — a red suite means no model ships.
- **Do not break the scoreboard's build-time read.** `src/pages/scoreboard.astro` reads `data/log.csv` via `process.cwd()`; keep that resolution.
- **Zero-JS home fallback must remain intact.** The static verdict `<h1>` and the native `<select>` must keep working if the island throws. This plan only touches island copy/estimate rendering, not the fallback.
- **JS unit-test runner is `bun test`** (files import `bun:test`; `nowcast.test.js` header says "Run with `bun test`"; `bun.lock` is committed). No task in this plan changes JS *logic* (`nowcast.js` is untouched) — the only `.astro` edits are inline island markup/copy, which `bun test` does not cover, so those tasks verify via `astro build`.
- **Commit style:** conventional prefixes (`fix:`/`feat:`/`refactor:`/`test:`/`chore:`). End every commit message with the trailer:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## Stop Boundaries (for incremental execution)

The user was weighing "safe labelling fixes only" vs "core bug only" vs "everything." Tasks are ordered so they can stop at any of these lines:

- **SAFE TO STOP AFTER TASK 4** — "safe labelling fixes only." Copy/resilience only: honest "measured now" label, HTTP retry/backoff, scoreboard freshness line, two doc-comment nits. No behavior change to the model, no data rewrite. Strictly-improving and low-risk.
- **CORE-BUG-ONLY STOP AFTER TASK 6** — the collector is fixed *forward-only*. New snapshots log the correct rolling-3h feature; historical rows remain mixed until Task 8. No data rewrite yet.
- **TASK 7** builds and unit-tests the backfill tool but does **not** run it (safe).
- **TASK 8 IS THE POINT OF NO EASY RETURN** — it **rewrites `data/log.csv`** (history) and **retrains/replaces `public/model.json`** (prod model). "Everything" tier.

---

## File Structure

| File | Task(s) | Responsibility / change |
| --- | --- | --- |
| `src/layouts/Almanac.astro` | 2 | Relabel "measured now" → honest estimate; show "—" instead of a fabricated `0.0 mm` when precipitation is unknown. Inline island only; fallback untouched. |
| `pipeline/sources.py` | 3, 6 | Task 3: add shared retry/backoff `requests.Session` + `_get()` choke point + 30s timeout; fix module docstring (labels are METAR VABB, not "NASA GPM IMERG"). Task 6: replace `fetch_recent_rain_mm` body with the correct rolling window; add pure `recent_rain_from_series()`. |
| `tests/test_sources.py` | 3, 6 | Task 3: assert the session's retry policy. Task 6: assert `recent_rain_from_series` mirrors the client (excludes current hour, None→0, clamps at series start). |
| `src/pages/scoreboard.astro` | 4 | Add a "Data through {last graded valid_at} IST" line beside the bake timestamp; fix the stale "daily build re-bakes" comment. Build-time only, zero-JS. |
| `pipeline/backfill_recent_rain.py` | 7 (create), 8 (run) | One-shot: re-derive `recent_rain_mm` for every historical row from one Open-Meteo `past_days` fetch and rewrite `data/log.csv`. Pure core `backfilled_rows()` + thin I/O `main()`. |
| `tests/test_backfill.py` | 7 | Fixture test for `backfilled_rows()` (no network). |
| `data/log.csv` | 8 (generated) | `recent_rain_mm` column rewritten by the backfill run. |
| `public/model.json` | 8 (generated) | Corrected model promoted by `pipeline/train.py` after backfill. |

---

## Task 1: Pre-flight — branch from `origin/main` and confirm live state

**Files:** none created/modified (establishes branch + verified state).

**Interfaces:**
- Consumes: nothing.
- Produces: a feature branch `fix/recent-rain-skew` whose `HEAD == origin/main`; confirmation that live `public/model.json` is `"type": "logistic"`; confirmation that `uv` and `bun` are on PATH.

- [ ] **Step 1: Fetch remote and branch from the REAL remote state (not the stale local tree)**

Run:
```bash
git fetch origin
git checkout -B fix/recent-rain-skew origin/main
git rev-parse --short HEAD
git rev-parse --short origin/main
```
Expected: the two `rev-parse` hashes are IDENTICAL. If they differ, STOP — you are not on `origin/main` and must not proceed (rewriting `data/log.csv` off a stale base clobbers a week of bot commits).

- [ ] **Step 2: Confirm the live champion model is logistic (guards the retrain gate assumptions)**

Run:
```bash
git show origin/main:public/model.json | grep '"type"'
```
Expected: `"type": "logistic",`

- [ ] **Step 3: Confirm the toolchain is present**

Run:
```bash
uv --version && bun --version
```
Expected: both print a version (e.g. `uv 0.x.y`, `1.x.y`). If `bun` is missing, JS-side verification (`astro build`) in Tasks 2 and 4 cannot run — install bun or stop before those tasks. If `uv` is missing, no Python task can run.

- [ ] **Step 4: Confirm the Python suite is green on the untouched base**

Run:
```bash
uv sync --frozen
uv run pytest -q
```
Expected: all tests pass (baseline green before any change). No commit — this task only establishes the branch and verified state.

---

## Task 2: Honest "measured now" label (cheap win — SAFE)

**Files:**
- Modify: `src/layouts/Almanac.astro:140` (the `<dt>` label) and `src/layouts/Almanac.astro:320-324` (`renderMeasured`).
- Test: none (inline island; `bun test` does not cover it). Verified via `astro build` + grep.

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: nothing consumed by later tasks.

**Why:** `renderMeasured` shows Open-Meteo `current.precipitation` — a model nowcast estimate — under the label "measured now", and fabricates `0.0 mm` when the value is absent. Both read as observed ground truth. This relabels it honestly and shows "—" when unknown.

- [ ] **Step 1: Write the failing verification (build + grep for the honest strings)**

There is no unit harness for the inline island, so the "test" is the build assertion. Run it now to confirm the OLD (dishonest) strings are what's present:
```bash
bun run build
grep -rl "measured now" dist/ && echo "OLD LABEL STILL PRESENT (expected before the fix)"
```
Expected BEFORE the fix: `grep` finds the string in a `dist/**/index.html` and prints `OLD LABEL STILL PRESENT (expected before the fix)`.

- [ ] **Step 2: Relabel the `<dt>` — `src/layouts/Almanac.astro:140`**

Replace:
```html
        <dt>measured now</dt>
```
with:
```html
        <dt>est. rain now</dt>
```

- [ ] **Step 3: Show "—" instead of a fabricated 0 — `src/layouts/Almanac.astro:320-324`**

Replace:
```js
    function renderMeasured(current) {
      const mm = current && typeof current.precipitation === "number"
        ? current.precipitation : 0;
      elMeasured.textContent = `${mm.toFixed(1)} mm`;
    }
```
with:
```js
    function renderMeasured(current) {
      // Open-Meteo current.precipitation is a MODEL estimate, not a station reading —
      // labelled "est. rain now". When it's missing, show "—", never a fabricated 0.
      const mm = current && typeof current.precipitation === "number"
        ? current.precipitation : null;
      elMeasured.textContent = mm === null ? "—" : `${mm.toFixed(1)} mm`;
    }
```

- [ ] **Step 4: Rebuild and verify the honest strings shipped, dishonest ones gone**

Run:
```bash
bun run build
grep -rl "est. rain now" dist/ && echo "NEW LABEL PRESENT"
grep -rl "measured now" dist/ || echo "OLD LABEL GONE"
```
Expected: prints `NEW LABEL PRESENT` (a `dist/**/index.html` path) and `OLD LABEL GONE`.

- [ ] **Step 5: Commit**

```bash
git add src/layouts/Almanac.astro
git commit -m "fix: label 'now' reading as a model estimate, not a measurement

Open-Meteo current.precipitation is model output; call it 'est. rain now'
and show '—' when absent instead of a fabricated 0.0 mm.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: HTTP retry/backoff + 30s timeout + docstring nit (cheap win — SAFE)

**Files:**
- Modify: `pipeline/sources.py:1-9` (docstring + imports), and insert a session/`_get` block after `BASE`; rewire `fetch_forecast` (`:41-44`) and the one GET in `fetch_recent_rain_mm` (`:53`) to use `_get`.
- Test: `tests/test_sources.py` (append one test).

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_get(url: str) -> requests.Response` — the single Open-Meteo GET choke point (shared session, retry/backoff, 30s timeout). Also module constants `TIMEOUT: int` and `_session: requests.Session`. **Task 6 consumes `_get` and `BASE`.**

**Why:** The `04:52` collector run failed with a `ReadTimeout` and no retry, dropping that hour's snapshot. One shared retrying session fixes all three call sites. The module docstring also wrongly claims labels come from "NASA GPM IMERG" — they come from METAR VABB (`pipeline/labels.py`).

- [ ] **Step 1: Write the failing test — `tests/test_sources.py`**

Append:
```python
def test_get_session_has_retry_and_backoff():
    # A transient 5xx/timeout must not drop a whole hourly snapshot: the shared
    # session retries with backoff. (No network — inspect the mounted adapter.)
    from pipeline.sources import _session, TIMEOUT
    retries = _session.get_adapter("https://api.open-meteo.com/v1/forecast").max_retries
    assert retries.total == 3
    assert retries.backoff_factor >= 1.0
    assert 429 in retries.status_forcelist and 503 in retries.status_forcelist
    assert TIMEOUT >= 30
```

- [ ] **Step 2: Run it, verify it FAILS**

Run:
```bash
uv run pytest -q tests/test_sources.py::test_get_session_has_retry_and_backoff
```
Expected: FAIL with `ImportError: cannot import name '_session'` (or `TIMEOUT`) from `pipeline.sources`.

- [ ] **Step 3: Fix the docstring + add the retrying session — `pipeline/sources.py:1-9`**

Replace lines 1–9:
```python
"""The only module that talks to Open-Meteo.

Open-Meteo is a free, keyless delivery pipe for global weather models (GFS, ICON,
ECMWF incl. the AIFS AI model) — NOT a source of ground truth. Every value here is
model output. Truth/labels come from NASA GPM IMERG on the CI path (see pipeline/labels).
"""
import requests

BASE = "https://api.open-meteo.com/v1/forecast"
```
with:
```python
"""The only module that talks to Open-Meteo.

Open-Meteo is a free, keyless delivery pipe for global weather models (GFS, ICON,
ECMWF incl. the AIFS AI model) — NOT a source of ground truth. Every value here is
model output. Truth/labels come from METAR (NOAA Aviation Weather, station VABB) on
the CI path (see pipeline/labels).
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 30  # seconds; Open-Meteo can be slow under load (was 20 → ReadTimeout in CI)

# One shared session with retry/backoff so a transient 5xx or read-timeout doesn't drop
# a whole hourly snapshot. backoff_factor=1 → sleeps 0s, 2s, 4s between the 3 attempts.
_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=1.0,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
)))


def _get(url: str):
    """Single choke point for every Open-Meteo GET: shared session, retry/backoff, timeout."""
    return _session.get(url, timeout=TIMEOUT)
```

- [ ] **Step 4: Rewire the three call sites to `_get` — `pipeline/sources.py`**

In `fetch_forecast` (originally `:41-44`), replace:
```python
def fetch_forecast(lat: float, lon: float) -> dict:
    raw_best = requests.get(build_forecast_url(lat, lon), timeout=20).json()
    raw_ecmwf = requests.get(_ecmwf_url(lat, lon), timeout=20).json()
    return parse_forecast(raw_best, raw_ecmwf)
```
with:
```python
def fetch_forecast(lat: float, lon: float) -> dict:
    raw_best = _get(build_forecast_url(lat, lon)).json()
    raw_ecmwf = _get(_ecmwf_url(lat, lon)).json()
    return parse_forecast(raw_best, raw_ecmwf)
```

In `fetch_recent_rain_mm` (originally `:53`), replace the single line:
```python
    vals = requests.get(url, timeout=20).json()["hourly"]["precipitation"]
```
with:
```python
    vals = _get(url).json()["hourly"]["precipitation"]
```
(Leave the rest of `fetch_recent_rain_mm` unchanged for now — Task 6 replaces its body. If you are stopping after Task 4, the function still works via `_get`, just with the old window.)

- [ ] **Step 5: Run tests, verify PASS**

Run:
```bash
uv run pytest -q tests/test_sources.py
```
Expected: PASS (the new test plus the three existing `test_sources` tests).

- [ ] **Step 6: Commit**

```bash
git add pipeline/sources.py tests/test_sources.py
git commit -m "fix: retry/backoff + 30s timeout on Open-Meteo GETs; correct labels docstring

Shared retrying requests.Session via _get() so a transient timeout (the CI
04:52 ReadTimeout) no longer drops an hourly snapshot. Labels are METAR VABB,
not NASA GPM IMERG.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Scoreboard freshness line + stale-comment nit (cheap win — SAFE)

**Files:**
- Modify: `src/pages/scoreboard.astro:5-6` (comment), insert after `:91` (frontmatter `builtAt`), insert after `:284` (markup).
- Test: none (build-time Astro frontmatter). Verified via `astro build` + grep.

**Interfaces:**
- Consumes: existing frontmatter `labelled: Row[]` (defined at `:59`) and the existing `.sb-built` CSS class (no new CSS).
- Produces: nothing consumed by later tasks.

**Why:** The board only shows the UTC bake time; a Mumbai user can't tell whether recent rain is missing because it's stale or broken (complaint A). A "Data through {last graded hour} IST" line makes staleness legible. The header comment claiming a "daily" rebuild is stale — every push to `main` (the hourly collector, ~10×/day) triggers a Vercel rebuild.

- [ ] **Step 1: Write the failing verification (build + grep)**

Run now to confirm the freshness line is absent before the change:
```bash
bun run build
grep -rl "Data through" dist/ || echo "NO FRESHNESS LINE YET (expected before the fix)"
```
Expected BEFORE the fix: prints `NO FRESHNESS LINE YET (expected before the fix)`.

- [ ] **Step 2: Fix the stale header comment — `src/pages/scoreboard.astro:5-6`**

Replace:
```
// is computed AT BUILD TIME from data/log.csv, so the daily GitHub Actions
// build re-bakes the board. Nothing here runs in the browser. The <head> +
```
with:
```
// is computed AT BUILD TIME from data/log.csv, so every push to main (the hourly
// collector commits ~10×/day) triggers a Vercel rebuild that re-bakes the board.
// Nothing here runs in the browser. The <head> +
```

- [ ] **Step 3: Compute the freshness stamp in the frontmatter — insert after `src/pages/scoreboard.astro:91`**

After the line:
```js
const builtAt = new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC";
```
insert:
```js
// Freshness: the most recent forecast-hour that has actually been graded, so a
// visitor sees how current the board is — not just when it was baked. valid_at is
// an IST "YYYY-MM-DDTHH:00" string (Asia/Kolkata), so lexical max = chronological max.
const lastGraded = labelled.reduce((m, r) => (r.valid_at > m ? r.valid_at : m), "");
const dataThrough = lastGraded ? lastGraded.replace("T", " ") + " IST" : null;
```

- [ ] **Step 4: Render the line next to the bake time — insert after `src/pages/scoreboard.astro:284`**

After the line:
```html
    <p class="sb-built">Baked at build · {builtAt}</p>
```
insert:
```html
    {dataThrough && <p class="sb-built">Data through {dataThrough}</p>}
```

- [ ] **Step 5: Rebuild and verify the line shipped**

Run:
```bash
bun run build
grep -rl "Data through" dist/ && echo "FRESHNESS LINE PRESENT"
```
Expected: prints a `dist/**` path and `FRESHNESS LINE PRESENT`. (The board reads the branch's current `data/log.csv`, which has ~1410 labelled rows, so `dataThrough` is non-null.)

- [ ] **Step 6: Commit**

```bash
git add src/pages/scoreboard.astro
git commit -m "feat: scoreboard 'Data through <hour> IST' freshness line; fix stale rebake comment

Shows the most recent graded hour so staleness reads as staleness, not breakage
(complaint A). Corrects the comment: every push (~10x/day), not a daily build,
re-bakes the board on Vercel.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

> **SAFE TO STOP HERE (Task 4).** Everything above is copy/resilience only — no model change, no data rewrite. Tasks 5+ change collector behavior and (Task 8) rewrite data + retrain prod.

---

## Task 5: Merge/PR checkpoint for the safe tier (operational — optional early ship)

**Files:** none.

**Interfaces:**
- Consumes: commits from Tasks 2–4.
- Produces: an optionally-mergeable PR containing only the safe tier.

**Why:** This is the incremental-delivery seam. If the user wants "safe labelling fixes only," open the PR here; the core fix continues on the same branch and can be a second PR.

- [ ] **Step 1: Confirm the safe tier is green and self-contained**

Run:
```bash
uv run pytest -q
bun run build
git log --oneline origin/main..HEAD
```
Expected: pytest passes; build succeeds; `git log` shows exactly the three commits from Tasks 2, 3, 4.

- [ ] **Step 2: (Optional) open the safe-tier PR**

Run (only if shipping the safe tier now):
```bash
git push -u origin fix/recent-rain-skew
gh pr create --fill --title "Safe honesty/resilience fixes (measured-now label, HTTP retries, scoreboard freshness)"
```
Expected: a PR URL is printed. No code change; this task is a checkpoint. If continuing straight to the core fix, skip Step 2 and proceed to Task 6.

---

## Task 6: Core fix — correct the `recent_rain_mm` window (CORE BUG)

**Files:**
- Modify: `pipeline/sources.py` — add pure `recent_rain_from_series`; replace `fetch_recent_rain_mm` body (originally `:47-55`).
- Test: `tests/test_sources.py` (append four tests).

**Interfaces:**
- Consumes: `_get(url)`, `BASE`, `TIMEOUT` from Task 3.
- Produces:
  - `recent_rain_from_series(times: list[str], precip: list[float | None], now_stamp: str) -> float` — pure; sums precip over the 3 hours strictly BEFORE `now_stamp`, treating non-numeric as 0, rounded to 2 dp. **Task 7 consumes this.**
  - `fetch_recent_rain_mm(lat: float, lon: float) -> float` — unchanged signature; now returns the rolling-3h value that mirrors the browser.

**Why:** The old body used `past_days=1&forecast_days=0` then `vals[-3:]`, which is *yesterday 21:00–23:00 IST* — constant across every snapshot in an IST day (confirmed in `data/log.csv`: nine snapshots all read `4.9`). The browser's `shapeForecast()` (`src/layouts/Almanac.astro:219-224`) sums the 3 hours *before the current hour*. `recent_rain_mm` carries the model's largest weight (0.575), so this skew dominates wrong verdicts (complaint B).

- [ ] **Step 1: Write the failing tests — `tests/test_sources.py`**

Append:
```python
def test_recent_rain_sums_three_hours_before_now():
    from pipeline.sources import recent_rain_from_series
    times = ["2026-07-02T20:00", "2026-07-02T21:00", "2026-07-02T22:00",
             "2026-07-02T23:00", "2026-07-03T00:00"]
    precip = [1.0, 2.0, 3.0, 4.0, 9.9]
    # now = 23:00 → the 3 hours before it (20,21,22) = 6.0; the current hour is excluded.
    assert recent_rain_from_series(times, precip, "2026-07-02T23:00") == 6.0


def test_recent_rain_excludes_current_hour_mirrors_client():
    from pipeline.sources import recent_rain_from_series
    times = ["2026-07-02T21:00", "2026-07-02T22:00", "2026-07-02T23:00"]
    precip = [5.0, 5.0, 5.0]
    # now = 23:00 → i=2, window [max(0,-1):2] = hours 21,22 → 10.0 (mirrors precip.slice(i-3,i)).
    assert recent_rain_from_series(times, precip, "2026-07-02T23:00") == 10.0


def test_recent_rain_treats_none_as_zero():
    from pipeline.sources import recent_rain_from_series
    times = ["2026-07-02T20:00", "2026-07-02T21:00", "2026-07-02T22:00", "2026-07-02T23:00"]
    precip = [None, 2.0, None, 0.0]
    # now = 23:00 → window [20,21,22] = [None,2.0,None] → 2.0 (None counts as 0, like `v || 0`).
    assert recent_rain_from_series(times, precip, "2026-07-02T23:00") == 2.0


def test_recent_rain_near_series_start_clamps():
    from pipeline.sources import recent_rain_from_series
    times = ["2026-07-02T00:00", "2026-07-02T01:00"]
    precip = [3.0, 4.0]
    # now = 01:00 → i=1, window [max(0,-2):1] = [3.0] → 3.0 (fewer than 3 hours available).
    assert recent_rain_from_series(times, precip, "2026-07-02T01:00") == 3.0
```

- [ ] **Step 2: Run them, verify they FAIL**

Run:
```bash
uv run pytest -q tests/test_sources.py -k recent_rain
```
Expected: 4 FAIL with `ImportError: cannot import name 'recent_rain_from_series' from 'pipeline.sources'`.

- [ ] **Step 3: Implement — replace `fetch_recent_rain_mm` (originally `pipeline/sources.py:47-55`)**

Replace:
```python
def fetch_recent_rain_mm(lat: float, lon: float) -> float:
    """Sum of the last 3 hours of Open-Meteo precipitation — a FEATURE, not a label.
    (Circularity only matters for the label, which comes from METAR. The forecast's own
    recent value is a fine input — it's the strongest 0-2h predictor.)"""
    url = (f"{BASE}?latitude={lat}&longitude={lon}&hourly=precipitation"
           f"&past_days=1&forecast_days=0&timezone=Asia%2FKolkata")
    vals = _get(url).json()["hourly"]["precipitation"]
    recent = [v for v in vals[-3:] if isinstance(v, (int, float))]
    return round(sum(recent), 2)
```
with:
```python
def recent_rain_from_series(times, precip, now_stamp):
    """Pure. Sum precipitation over the 3 hours STRICTLY BEFORE `now_stamp`, mirroring
    the browser's shapeForecast() in src/layouts/Almanac.astro:
        i = first index whose hour >= now;  window = precip[i-3 : i];  None -> 0.
    `times` and `now_stamp` are IST 'YYYY-MM-DDTHH:MM' strings (Asia/Kolkata), compared
    on the 'YYYY-MM-DDTHH' hour prefix. Returns mm rounded to 2 dp (stored-column parity).
    This is a FEATURE, not a label — circularity only matters for the METAR label."""
    key = now_stamp[:13]
    i = next((k for k, t in enumerate(times) if t[:13] >= key), len(times) - 1)
    window = precip[max(0, i - 3):i]
    total = sum(v for v in window if isinstance(v, (int, float)))
    return round(total, 2)


def fetch_recent_rain_mm(lat: float, lon: float) -> float:
    """Rolling sum of the last 3 hours of precipitation, ending at (excluding) the current
    hour — the SAME window the browser computes in shapeForecast(), so the model is trained
    and served on the same feature. (Was: yesterday 21:00-23:00, constant across a day.)
    `current.time` is Open-Meteo's current IST instant, exactly what the client reads."""
    url = (f"{BASE}?latitude={lat}&longitude={lon}"
           f"&hourly=precipitation&current=precipitation"
           f"&past_days=1&forecast_days=1&timezone=Asia%2FKolkata")
    raw = _get(url).json()
    return recent_rain_from_series(
        raw["hourly"]["time"], raw["hourly"]["precipitation"], raw["current"]["time"])
```

- [ ] **Step 4: Run tests, verify PASS**

Run:
```bash
uv run pytest -q tests/test_sources.py
```
Expected: PASS — the 4 new `recent_rain` tests, the Task 3 retry test, and the 3 original tests.

- [ ] **Step 5: Commit**

```bash
git add pipeline/sources.py tests/test_sources.py
git commit -m "fix: recent_rain_mm is the rolling last-3h window, mirroring the client

Was yesterday 21:00-23:00 (constant per IST day) via past_days=1&forecast_days=0;
now sums the 3 hours before the current hour like shapeForecast(). Pure
recent_rain_from_series() unit-tested for the exclude-current-hour, None->0 and
series-start cases. Fixes the train/serve skew on the model's heaviest feature.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

> **CORE-BUG-ONLY STOP (Task 6).** The collector now logs the correct feature going forward. Historical rows are still mixed until Task 8 backfills them; the live model still expects the old feature until Task 8 retrains. Continue to fully fix.

---

## Task 7: Build & unit-test the backfill tool (SAFE — does not run it)

**Files:**
- Create: `pipeline/backfill_recent_rain.py`
- Test: `tests/test_backfill.py`

**Interfaces:**
- Consumes: `recent_rain_from_series` (Task 6); `_get`, `BASE` (Task 3); `_read`, `_write`, `LOG_PATH`, `LOG_HEADER`, `MUMBAI` (from `pipeline/log_snapshot.py`); `_utc_report_to_ist_hour` (from `pipeline/labels.py`).
- Produces:
  - `backfilled_rows(rows: list[dict], times: list[str], precip: list) -> list[dict]` — pure; returns NEW row dicts with `recent_rain_mm` recomputed per snapshot (`issued_at` → its IST hour → rolling-3h sum). Does not mutate input.
  - `main()` — reads `data/log.csv`, fetches one `past_days` series, rewrites the file. **Task 8 runs this.**

**Why:** After Task 6 the collector is correct forward-only; the ~6 days of historical `recent_rain_mm` are still the buggy constant. Training on a mixed column is worse than either pure version. This tool re-derives the historical column from the SAME data pipe (Open-Meteo forecast API `past_days`) the client and collector use — not ERA5 — so history matches serving. `issued_at` is a UTC stamp, so we reuse the tested `_utc_report_to_ist_hour` (appending `":00"` seconds it expects) to get each snapshot's IST hour.

- [ ] **Step 1: Write the failing test — `tests/test_backfill.py`**

Create `tests/test_backfill.py`:
```python
from pipeline.backfill_recent_rain import backfilled_rows


def test_backfilled_rows_recomputes_per_snapshot_and_is_pure():
    # IST hourly series with known precipitation.
    times = ["2026-07-02T20:00", "2026-07-02T21:00", "2026-07-02T22:00", "2026-07-02T23:00"]
    precip = [1.0, 2.0, 3.0, 9.9]
    # issued_at 18:00 UTC == 23:30 IST → now-hour 23:00 → sum of 20,21,22 = 6.0.
    rows = [
        {"issued_at": "2026-07-02T18:00", "valid_at": "2026-07-02T23:00", "recent_rain_mm": "999"},
        {"issued_at": "2026-07-02T18:00", "valid_at": "2026-07-03T02:00", "recent_rain_mm": "999"},
    ]
    out = backfilled_rows(rows, times, precip)
    assert out[0]["recent_rain_mm"] == 6.0
    assert out[1]["recent_rain_mm"] == 6.0          # same snapshot → same value
    assert out[0]["valid_at"] == "2026-07-02T23:00"  # other columns preserved
    assert rows[0]["recent_rain_mm"] == "999"        # input not mutated
```

- [ ] **Step 2: Run it, verify it FAILS**

Run:
```bash
uv run pytest -q tests/test_backfill.py
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.backfill_recent_rain'`.

- [ ] **Step 3: Implement — create `pipeline/backfill_recent_rain.py`**

```python
"""One-shot: recompute the recent_rain_mm column in data/log.csv with the CORRECTED
rolling-3h-before-now semantics (pipeline.sources.recent_rain_from_series). The old
collector wrote yesterday-21:00..23:00 for every snapshot; this rewrites the historical
column so the training set matches what the fixed collector now stores.

Data source is the SAME Open-Meteo forecast pipe (past_days) the client and collector
use — NOT ERA5 — so history stays consistent with serving. Run ONCE, from a branch
started at origin/main, then commit the rewritten log. Idempotent: re-running converges.
"""
from datetime import date

from pipeline.log_snapshot import _read, _write, LOG_PATH, MUMBAI
from pipeline.labels import _utc_report_to_ist_hour
from pipeline.sources import BASE, _get, recent_rain_from_series


def _span_past_days(rows) -> int:
    """How many past days to fetch to cover the oldest snapshot (+2 days margin, clamp 92)."""
    earliest_ist = min(_utc_report_to_ist_hour(r["issued_at"] + ":00") for r in rows)[:10]
    y, m, d = (int(x) for x in earliest_ist.split("-"))
    return max(1, min(92, (date.today() - date(y, m, d)).days + 2))


def _fetch_series(lat, lon, past_days):
    """One Open-Meteo call spanning the whole log; returns (times, precip) in IST."""
    url = (f"{BASE}?latitude={lat}&longitude={lon}&hourly=precipitation"
           f"&past_days={past_days}&forecast_days=1&timezone=Asia%2FKolkata")
    h = _get(url).json()["hourly"]
    return h["time"], h["precipitation"]


def backfilled_rows(rows, times, precip):
    """Pure: return NEW rows with recent_rain_mm recomputed per snapshot. Each row's
    issued_at (UTC) is converted to its IST hour, then the rolling-3h sum is read off
    the (times, precip) series. Cached per issued_at so a snapshot is computed once."""
    cache = {}
    out = []
    for r in rows:
        iss = r["issued_at"]
        if iss not in cache:
            now_stamp = _utc_report_to_ist_hour(iss + ":00")  # UTC stamp -> IST hour key
            cache[iss] = recent_rain_from_series(times, precip, now_stamp)
        r2 = dict(r)
        r2["recent_rain_mm"] = cache[iss]
        out.append(r2)
    return out


def main():
    rows = _read(LOG_PATH)
    if not rows:
        print("log.csv empty — nothing to backfill.")
        return
    times, precip = _fetch_series(MUMBAI[0], MUMBAI[1], _span_past_days(rows))
    new_rows = backfilled_rows(rows, times, precip)
    _write(LOG_PATH, new_rows)
    changed = sum(1 for a, b in zip(rows, new_rows)
                  if str(a["recent_rain_mm"]) != str(b["recent_rain_mm"]))
    print(f"backfilled recent_rain_mm: {changed}/{len(rows)} rows changed.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests, verify PASS**

Run:
```bash
uv run pytest -q tests/test_backfill.py
```
Expected: PASS. Then run the full suite to confirm nothing regressed:
```bash
uv run pytest -q
```
Expected: all pass.

- [ ] **Step 5: Commit (the tool, not yet run)**

```bash
git add pipeline/backfill_recent_rain.py tests/test_backfill.py
git commit -m "feat: one-shot backfill tool for the recent_rain_mm column

Pure backfilled_rows() recomputes recent_rain_mm per snapshot from one Open-Meteo
past_days series (same pipe as serving), reusing _utc_report_to_ist_hour and
recent_rain_from_series. Fixture-tested; not yet executed against data/log.csv.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Run backfill + retrain + promote (REWRITES DATA + RETRAINS PROD)

**Files (generated, not hand-edited):**
- Modify: `data/log.csv` (backfill rewrites the `recent_rain_mm` column).
- Modify: `public/model.json` (retrain promotes a corrected model).
- Test: verification commands below (operational; not unit TDD).

**Interfaces:**
- Consumes: `pipeline/backfill_recent_rain.py` `main()` (Task 7); `pipeline/train.py` `main()` (existing).
- Produces: a corrected committed `data/log.csv` and `public/model.json`.

> **POINT OF NO EASY RETURN.** This rewrites the bot's committed history and replaces the live model. Confirm `git rev-parse HEAD` still descends from `origin/main` (Task 1) before running. Old values remain recoverable in git history, but do not run this off a stale base.

- [ ] **Step 1: Snapshot the "before" state (so the diff is reviewable)**

Run:
```bash
git show origin/main:data/log.csv | tail -n 5
uv run python -c "import csv;rows=list(csv.DictReader(open('data/log.csv')));import collections;print('distinct recent by issued_at (sample):',dict(list({r['issued_at']:r['recent_rain_mm'] for r in rows}.items())[-8:]))"
```
Expected: the sampled `recent_rain_mm` values are CONSTANT across each `issued_at` (the bug — e.g. several `4.9`s).

- [ ] **Step 2: Run the backfill (rewrites `data/log.csv`)**

Run:
```bash
uv run python -m pipeline.backfill_recent_rain
```
Expected: prints `backfilled recent_rain_mm: N/M rows changed.` with `N` a large fraction of `M` (most rows had the wrong constant). If it prints `0/M`, STOP and investigate — the fetch or conversion is wrong.

- [ ] **Step 3: Verify the rewrite is sane (values now vary within a snapshot's neighborhood, columns intact)**

Run:
```bash
uv run pytest -q            # pure functions still green after the tool ran
uv run python -c "import csv;rows=list(csv.DictReader(open('data/log.csv')));vals={r['issued_at']:r['recent_rain_mm'] for r in rows};print('distinct recent values now:',len(set(vals.values())),'across',len(vals),'snapshots');assert all(set(r.keys())>= {'issued_at','valid_at','recent_rain_mm','observed_raining'} for r in rows)"
git diff --stat data/log.csv
```
Expected: many more distinct `recent_rain_mm` values than the near-constant "before"; `git diff --stat` shows ONLY `data/log.csv` changed. Manually skim `git diff data/log.csv` to confirm only the `recent_rain_mm` column moved (other columns byte-identical).

- [ ] **Step 4: Retrain on the corrected data and promote (rewrites `public/model.json`)**

Run:
```bash
uv run python -m pipeline.train
```
Expected: prints a `candidate Brier=... raw-forecast=... champion=...` line followed by `PROMOTED — beats raw forecast AND champion.` and `public/model.json` now has a fresh `trained_at`.
- If instead it prints `Rejected — did not beat both baselines. Champion kept.`: do NOT hack the gate. The corrected candidate is the right model; the conservative gate simply didn't clear on this holdout. Leave `public/model.json` as-is, commit only the corrected `data/log.csv` (Step 6 without the model), and let the next daily `retrain.yml` cron promote once a few more corrected rows accrue. Note this in the PR.

- [ ] **Step 5: Confirm the promoted model is well-formed and schema-stable**

Run:
```bash
uv run python -c "import json;m=json.load(open('public/model.json'));assert m['type']=='logistic';assert m['features']==['fc_bestmatch_mm','fc_ecmwf_mm','hour_sin','hour_cos','recent_rain_mm'];assert len(m['weights'])==5;print('trained_at',m['trained_at'],'brier',m['brier'],'raw',m['raw_brier'],'champ',m['champion_brier'])"
```
Expected: no assertion error; prints a `trained_at` newer than the pre-existing `2026-07-03T05:05:43Z` and a `brier` <= `raw_brier`.

- [ ] **Step 6: Commit the corrected data (and model, if promoted)**

Run:
```bash
git add data/log.csv public/model.json
git commit -m "fix: backfill recent_rain_mm history and retrain on corrected data

Ran pipeline.backfill_recent_rain to rewrite the historical recent_rain_mm column
to the rolling-3h semantics, then pipeline.train promoted a model trained/served on
the same feature. Closes the train/serve skew (complaint B). [skip ci]

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
(If Step 4 was Rejected, drop `public/model.json` from `git add`.)

- [ ] **Step 7: Post-merge CI confirmation (after this branch merges to `main`)**

Once merged to `main`, confirm CI reproduces promotion (workflow_dispatch exists in `retrain.yml`):
```bash
gh workflow run retrain
gh run watch $(gh run list --workflow=retrain --limit 1 --json databaseId --jq '.[0].databaseId')
```
Expected: the run's "Train + eval gate" step prints the same `PROMOTED`/`Rejected` outcome; on promote it commits `model: retrain promoted [skip ci]` and Vercel rebuilds the live site with the corrected model. This step is confirmation only — the in-branch commit from Step 6 already carries the fix.

---

## Self-Review

**1. Spec coverage** (every item from the coordinator's scope → task):

| Spec item | Task |
| --- | --- |
| Correct `fetch_recent_rain_mm` to rolling last-3h ending at current hour, mirroring `shapeForecast` | 6 |
| Refactor windowing into a PURE, unit-testable function | 6 (`recent_rain_from_series`, 4 tests) |
| One-shot backfill of `recent_rain_mm` from Open-Meteo past_days + rewrite file | 7 (build+test), 8 (run) |
| Backfill test on a fixture | 7 (`tests/test_backfill.py`) |
| Retrain trigger `gh workflow run retrain`, verify promote + `model.json` updates | 8 (Step 4 local promote + Step 7 CI trigger) |
| Cheap win: relabel "measured now" as estimate | 2 |
| Cheap win: HTTP retry/backoff + longer timeout on the 3 `requests.get` | 3 |
| Cheap win: scoreboard "data through … IST" line | 4 |
| Doc nit: sources.py "NASA GPM IMERG" → METAR VABB | 3 (folded — same file) |
| Doc nit: scoreboard "daily build re-bakes" stale comment | 4 (folded — same file) |
| CRITICAL hazard: branch from `origin/main`, confirm logistic model, verify line numbers vs remote | 1 |
| Sequenced for incremental stop points | Stop Boundaries section + Task 5 seam; safe=≤4, core=≤6, everything=8 |
| State the JS test runner exactly | Global Constraints (`bun test`; no JS-logic change → `.astro` verified via `astro build`) |
| Python test command | `uv run pytest -q` throughout (matches `retrain.yml`) |

No gaps found.

**2. Placeholder scan:** No `TBD`/`TODO`/"add validation"/"similar to Task N"/"handle edge cases". Every code and test step shows actual code; every verification step shows an exact command and expected output. Operational tasks (1, 5, 8) that don't fit pure TDD each carry concrete commands + expected output as their "test." PASS.

**3. Type consistency:**
- `recent_rain_from_series(times, precip, now_stamp) -> float` — defined Task 6, consumed identically in Task 7 (`backfilled_rows`) and its wrapper. ✓
- `_get(url) -> Response` — defined Task 3, consumed in Task 6 wrapper and Task 7 `_fetch_series`. ✓
- `backfilled_rows(rows, times, precip) -> list[dict]` — defined Task 7, asserted in `tests/test_backfill.py` (Task 7) with matching arg order. ✓
- Reused symbols exist on `origin/main`: `_read`/`_write`/`LOG_PATH`/`LOG_HEADER`/`MUMBAI` (log_snapshot.py), `_utc_report_to_ist_hour` (labels.py), `BASE` (sources.py), `train.main` (train.py). ✓ (`LOG_HEADER` imported in file-structure note but not needed by the code as written — `_write` already closes over it; not imported in `backfill_recent_rain.py`, so no unused import. ✓)
- Feature-name list asserted in Task 8 Step 5 matches the Global Constraints order and `train.py` `FEATURE_NAMES`. ✓
- `_utc_report_to_ist_hour` requires `"%Y-%m-%dT%H:%M:%S"` (19 chars); `issued_at` is 16 chars, so Task 7 passes `iss + ":00"` — consistent between `_span_past_days`, `backfilled_rows`, and the fixture test's 18:00→23:00 expectation. ✓

No inconsistencies found. Plan is internally complete and executable by a reviewer with zero codebase context.
