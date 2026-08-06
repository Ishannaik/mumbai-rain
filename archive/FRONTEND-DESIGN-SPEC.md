# Frontend Design Spec — Mumbai Rain App

The **visual design system** (palette, type, layout, motion). For the *what-goes-where* product spec, see `FRONTEND-SPEC.md`. This doc is the *how-it-looks*.

**Direction in one line:** Mumbai's monsoon sky + the meteorologist's radar scale + rising flood-water — the screen literally *reads like a rain radar tuned to your street.*

---

## 1. Color — grounded in the IMD radar reflectivity scale

The background is the Arabian-Sea storm sky. The **accent is not fixed** — it's the live rain reading, pulled from the actual dBZ color ramp Indian meteorologists use. Color = information, not decoration.

**Surfaces (always-on):**
| Token | Hex | What it is |
|---|---|---|
| `--sky-deep` | `#0d1b1e` | Sea-storm charcoal-teal — the background (NOT pure black) |
| `--sky-raised` | `#14282b` | Lifted panels / rows |
| `--mist` | `#dce6e3` | Primary text (rain-haze near-white) |
| `--wet-stone` | `#6b8385` | Secondary text / labels (grey-green) |

**The verdict accent — driven by state, off the radar ramp:**
| State | Token | Hex | Source |
|---|---|---|---|
| Dry / safe | `--clear` | `#a9c4bf` | Sea-glass calm (off the rain ramp) |
| Rain coming | `--rain` | `#4ea8d6` | Radar light-moderate blue |
| Raining now | `--heavy` | `#ffd23f → #ff8c2a` | Radar yellow→orange, escalates with mm/h |
| Flood risk | `--flood` | `#e23b3b` | Radar red — reserved, flood line + rising water only |

> Rule: only ONE accent shows at a time (the current state). The whole hero recolors to it. `--flood` red never appears except for genuine flood risk — that's what makes it mean something.

---

## 2. Typography — a station indicator board + a Marathi anchor

| Role | Typeface | Why |
|---|---|---|
| **Display (the verdict)** | **Saira** (condensed, heavy/800) | Technical, condensed — reads like a Mumbai local-train indicator board |
| **Cultural eyebrow** | **Mukta** (Devanagari), small | The word **पाऊस** ("rain" in Marathi) sits above the verdict — grounds it in Mumbai, not a generic city |
| **Body** | Inter / system-ui | Quiet, legible, gets out of the way |
| **Data / readings** | **Spline Sans Mono** | Station mm, distances, model version — instrument/readout feel |

**Type scale (mobile-first):** verdict `clamp(2.8rem, 12vw, 4.5rem)` · section labels `0.75rem` uppercase tracked-out · body `1rem` · data `0.85rem` mono.

The verdict is the loudest thing on the page by far. Everything else is whispered.

---

## 3. Layout — a phone-height "rain ticket"

```
┌───────────────────────────┐
│ पाऊस            📍 Bandra ▾│  ← Marathi eyebrow + location pill (small)
│                           │
│                           │
│     RAIN IN ~40 MIN       │  ← THE VERDICT (huge, recolors by state)
│       ~3 mm/h             │     fills ~45% of screen
│                           │
│  ▸ Leave in next 15 min   │  ← leave-now strip (only if rain coming)
│                           │
│ ─────────────────────────  │
│ measured now   0.0mm·2km   │  ← ground reality (mono data, quiet)
│ ⚠ Hindmata pooling likely  │  ← flood line (only if risky, --flood red)
│ ─────────────────────────  │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░  │  ← THE RISING WATER (signature, see §4)
│ calibrated · scoreboard ·  │  ← footer: honesty + attribution
│ Weather data by Open-Meteo │
└───────────────────────────┘
```

Big answer up top, quiet detail below, water at the base. Single column, thumb-reachable.

---

## 4. Signature element — "The Rising Water"

A horizontal water line anchored to the **bottom of the viewport** that physically **rises up the screen as flood risk increases**:
- Dry/low → a thin calm line at the very base.
- Watch → water climbs ~15%, gentle ripple.
- High flood risk → water visibly risen (~30%), tinted `--flood` red, slow swell.

It literally visualizes Mumbai's defining problem — *water rising in the street* — and ties rain + tide together. This is the one memorable, subject-specific moment. Everything else stays disciplined and quiet around it.

(Replaces the generic "rain falling" canvas — falling rain is what every weather app does; *rising water* is what Mumbai actually fears.)

---

## 5. Motion (restrained)
- **Page load:** verdict fades + counts up from "…" to the answer (~600ms). One orchestrated moment.
- **Water:** slow ambient swell only. No bouncing, no particles.
- **State change:** hero color cross-fades (~400ms) when location/data changes.
- `prefers-reduced-motion` → water renders as one static line, no animation.

---

## 6. Quality floor (non-negotiable, unstated in UI)
Responsive to 320px width · visible keyboard focus rings · contrast ≥ 4.5:1 on text · reduced-motion respected · works one-handed.

---

## 7. Why this isn't a generic AI default
- **Not "black + one bright accent"** (AI default #2): background is sea-storm *teal*, and the accent is *state-driven from the radar scale*, not a fixed brand color.
- **Not generic weather-blue + white cards:** dark monsoon-sky field, station-board type, Marathi anchor.
- **The signature is the subject, not an effect:** rising flood-water (Mumbai's real fear), not falling-rain decoration.
- **Every color is derived:** surfaces from the storm sky, accents from the IMD radar dBZ ramp — choices made for *this* brief.
