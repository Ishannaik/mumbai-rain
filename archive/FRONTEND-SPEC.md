# Frontend Spec Sheet — Mumbai Rain App

Plain-language spec for the frontend-design skill / a build subagent. Read top to bottom.

---

## 1. What this app is (in one sentence)
A phone-first web page that answers ONE question in 2 seconds: **"Will it rain at my exact spot in the next 2 hours — should I leave now?"**

## 2. The golden rule
**One big answer. Everything else is small.** If a user glances for 2 seconds and walks away knowing whether to grab an umbrella, the design won. No clutter, no dashboard, no 10 numbers competing for attention.

## 3. Who uses it
A Mumbai person, on their phone, about to step out. Monsoon season. They don't care about meteorology — they care about: *do I leave now, or wait 20 minutes?*

---

## 4. The screen, top to bottom

| # | Element | What it shows | Why it's there |
|---|---------|---------------|----------------|
| 1 | **Location pill** (top, small) | "📍 Bandra ▾" — auto-detected, tappable to change | User must trust it's *their* spot |
| 2 | **THE VERDICT** (hero, huge) | "Dry for 2 hours" / "Rain in ~40 min" / "Raining now" | The whole point. Dominates the screen. |
| 3 | **Leave-now line** (only if rain coming) | "Leave in the next 15 min to stay dry" | Turns a forecast into a *decision* |
| 4 | **Ground reality** (small) | "Measured now: 0mm at a station 2km away" | Honesty — real measurement, not just a guess |
| 5 | **Flood line** (only if risky) | "⚠️ Hindmata pooling likely" | Mumbai-specific value nobody else gives |
| 6 | **Footer** (tiny) | "calibrated for your spot · how we score ourselves" + "Weather data by Open-Meteo.com" | Trust + legally-required credit |

If it's dry and calm: only #1, #2, #6 show. Sections #3–#5 appear only when relevant.

---

## 5. The three states (the verdict changes look by state)
- **DRY** → calm, warm, reassuring. "Dry for the next 2h ☀️"
- **RAIN COMING** → alert but not panic. "Rain in ~40 min · ~3mm/h"
- **RAINING NOW** → immediate. "Raining now · ~5mm/h"

The *color of the screen itself* should signal the state before the user even reads the words.

---

## 6. Design vibe (the feel)
- **Mumbai, not generic weather-app.** Avoid the default sky-blue + white-card look every weather app uses.
- **Calm and fast.** Feels instant. No spinners spinning forever.
- **Big answer, small detail.** Huge type for the verdict; quiet small type for everything else.
- **Mobile-first.** Designed for a thumb on a phone, not a desktop.
- **Feels installable** (like a real app on the home screen), not a webpage.

## 7. Must-haves
- Loading state while it figures out location + weather ("Reading the sky…").
- Graceful failure: if location is denied or the data fails, say so kindly + offer the dropdown / a retry.
- Works one-handed on a phone. Big tap targets.
- Accessible: readable contrast, respects "reduce motion" if there's any animation.

## 8. Do NOT
- ❌ No ads, no popups, no login, no cookie banner.
- ❌ No wall of hourly numbers as the main view (that's the *detail*, not the answer).
- ❌ No generic stock weather icons as the centerpiece.
- ❌ Don't make the user tap anything to get the basic answer — it loads ready.

---

## 9. Tech constraints (hard rules)
- **Static site** — plain HTML + CSS + vanilla JS. No React, no framework, no build step.
- **< 100KB total page weight.** Fast on Mumbai mobile data.
- **Data:** browser calls Open-Meteo directly (free, no key). Plus our own tiny `model.json` for the calibration.
- **Reuses existing logic files:** `nowcast.js` (the verdict), `flood.js` (flood risk), `model.json`, `data/localities.json`, `data/flood-zones.json`.
- **Required credit** in footer: `Weather data by Open-Meteo.com` (linked).
- Deploys as static files (Cloudflare Pages).

## 10. Definition of done
Open it on a phone → within 2 seconds you see a clear rain verdict for your location, recolored by state, with the option to change locality — and it degrades gracefully if anything fails.
