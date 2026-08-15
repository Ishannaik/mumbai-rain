# Contributing

Thanks for looking. This is a small, deliberately narrow project: a rain nowcast for Mumbai only, with a public scoreboard so the claims can be checked. Contributions that keep it honest and specific are very welcome.

## Five-minute setup

Two independent halves. You only need the one you're touching.

### Web (Astro)

```bash
bun install          # or: npm install
bun run dev          # http://localhost:4321
```

Node 18+ or Bun. `bun run build` produces the production build.

### Pipeline (Python)

```bash
uv sync              # creates .venv and installs everything, including dev deps
uv run pytest -q
```

Python 3.11+, managed with [`uv`](https://docs.astral.sh/uv/) — no hand-rolled venv paths.

If `uv` is new to you: `uv sync` replaces `python -m venv` + `pip install`, and `uv run <cmd>` runs `<cmd>` inside that environment without activating it.

## Running the tests

```bash
uv run pytest -q                       # the whole suite
uv run pytest tests/test_train.py -q   # one file
```

`tests/` is pytest over `pipeline/`. There is no test suite for the Astro side yet, so web changes are verified by running `bun run dev` and looking.

**Windows note:** several pipeline modules print `≥` and `→`, which a default `cp1252` console cannot encode, so a command can die with `UnicodeEncodeError` before printing its summary. Prefix with `PYTHONIOENCODING=utf-8` if you hit it. CI runs on Linux with UTF-8 and never sees this.

## How health and the scoreboard work

These two are how the project keeps itself accountable, so it helps to run them before proposing a change to the pipeline.

```bash
uv run python -m pipeline.health          # summary, and writes public/metrics.json
uv run python -m pipeline.health --fail-stale 12
uv run python -m pipeline.train           # retrain; promotes only if it earns it
```

`pipeline/health.py` prints one line per concern and exits non-zero when something is wrong, which is what CI gates on:

```
collect     last=... stale_h=1.47  level=ok  gaps>1h=171 max=511.0h
model       type=logistic  trained_at=...  stored_brier=0.1941
holdout     n_test=836  model=0.186  raw=0.4701  clim=0.2672  status=ok
bss         vs_raw=0.6044  vs_clim=0.3039
go_live     data=True logistic=True beats_raw=True beats_clim=True fresh=True
```

It also writes `public/metrics.json`, which the site serves at `/metrics.json` and `/scoreboard` renders. So the scoreboard is not a separate calculation — change the numbers in `health.py` and the page follows.

`pipeline/train.py` trains a candidate and **only** overwrites `public/model.json` if the candidate beats the raw forecast, climatology, and the current champion, across walk-forward folds with a purge gap. A candidate that wins one lucky week does not get promoted. Running it locally is safe to inspect, but note that a passing candidate **will** rewrite `public/model.json` — check `git status` afterwards and revert if you did not mean to commit a retrain.

## The data is the database

`data/log.csv` grows hourly via `.github/workflows/collect.yml`. Treat it as append-only: don't rewrite history, and don't reformat it in a PR, because every diff there is also a change to the training set.

## What makes a good PR

- **One concern per PR.** Easier to review, easier to revert.
- **Say how you verified it.** For pipeline work, the numbers before and after. For web work, what you clicked.
- **Don't widen the scope.** "Mumbai only" and "no API keys on the live path" are deliberate constraints, not gaps.
- **No silent magic.** If a change affects the published probability, the method has to stay explainable on `/about` and checkable on `/scoreboard`.

Tests are expected for pipeline logic. If a change is hard to test, say so in the PR rather than skipping it quietly.

## First PR ideas

Issues are labelled — start here:

- [good first issue](https://github.com/Ishannaik/mumbai-rain/labels/good%20first%20issue) — scoped, with hints in the body
- [docs](https://github.com/Ishannaik/mumbai-rain/labels/docs) — wording, setup, explanation
- [help wanted](https://github.com/Ishannaik/mumbai-rain/labels/help%20wanted) — open to anyone

Before starting something larger, comment on the issue so two people don't build it twice.

## Code of conduct

Be decent. Assume good faith, keep review about the work, and accept that "no" to a feature is usually about scope rather than about you.
