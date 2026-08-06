# पाऊस · Mumbai Rain

**Will it rain at your exact Mumbai spot in the next 2 hours?**

Live site: **[rain.ishannaik.com](https://rain.ishannaik.com)**

A hyperlocal, ad-free, no-install nowcast for Mumbai. One verdict in ~2 seconds — leave now or wait — plus a flood-risk watch for nearby low spots. Runs at **$0** (static site + free forecast API + free GitHub Actions crons).

## What it is

| Layer | What happens |
|-------|----------------|
| **Browser** | Fetches a keyless [Open-Meteo](https://open-meteo.com/) forecast, applies a tiny exported model (`public/model.json`) as plain arithmetic |
| **Model** | Calibrated logistic classifier — bias-corrects global forecasts for Mumbai microclimate |
| **Truth** | METAR present-weather at VABB (Mumbai airport), not another forecast — so labels stay independent |
| **Brain** | Hourly cron appends rows to `data/log.csv`; daily retrain promotes a new model **only** if it beats the champion and raw baseline on a holdout |
| **API** | `GET /api/nowcast?lat=&lon=` (or `?locality=bandra`) — same math as the UI |

Honest claims and limits: **[/about](https://rain.ishannaik.com/about)** · live skill: **[/scoreboard](https://rain.ishannaik.com/scoreboard)**

## Repo map

```
mumbai-rain/
  src/                 # Astro app (pages, layouts, client libs)
  public/              # Static assets + model.json + localities/flood zones
  pipeline/            # Python: fetch → log → label → train → promote
  data/log.csv         # Growing training diary (git = database)
  tests/               # pytest
  .github/workflows/   # hourly collect + daily retrain
  docs/og/             # Source for the social preview card
  archive/             # Old plans & design prototypes (not product docs)
```

## Health check (logs + model)

```bash
uv run python -m pipeline.health          # summary + writes public/metrics.json
uv run python -m pipeline.health --fail-stale 12
uv run python -m pipeline.train           # dry-run promotion gate
```

Public scoreboard: https://rain.ishannaik.com/scoreboard · machine-readable: `/metrics.json`

## Quick start

### Web (Astro)

```bash
bun install          # or: npm install
bun run dev          # http://localhost:4321
bun run build
```

Requires Node 18+ (or Bun). Deploys on Vercel (`@astrojs/vercel`); most pages are static; `/api/nowcast` is on-demand.

### Pipeline (Python)

```bash
uv sync
uv run pytest -q
uv run python -m pipeline.log_snapshot   # one forecast + label row
uv run python -m pipeline.train          # retrain; promote only if better
```

Python 3.11+. Uses `uv` — no hand-rolled venv paths.

## API

```http
GET /api/nowcast?lat=19.06&lon=72.83&hours=2
GET /api/nowcast?locality=bandra&hours=3
```

Returns JSON: calibrated rain probability, verdict text, flood-risk nearest zone, and the inputs used. Same modules as the UI (`nowcast.js`, `flood.js`, `open-meteo.js`).

## Model

`public/model.json` is a few KB of weights:

- Features: `fc_bestmatch_mm`, `fc_ecmwf_mm`, hour sin/cos, `recent_rain_mm`
- Serve path: `sigmoid(w · x + b)` in the browser — no ML runtime on the live path
- Promotion gate: walk-forward holdout; must beat current champion **and** raw forecast

## Design notes

- **Mumbai only** — hyperspecialized, not a global weather app
- **No API keys on the live path** — Open-Meteo is keyless and CORS-friendly
- **No silent “AI magic”** — method, data split, and scoreboard are public
- Product voice and method: site `/about`; early specs live under `archive/`

## License

[MIT](./LICENSE) · Weather data by [Open-Meteo](https://open-meteo.com/)
