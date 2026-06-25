This is a synthesis task, not a coding task. I have all the research I need in the prompt. Let me write the strategy doc directly.

# HOW TO WIN: Mumbai 0-2h Rain Project

## 1. The Winning Thesis

Win by being the **fastest, ad-free, no-install, single-spot "should I leave now?" verdict for Mumbai** — backed by an *honestly-calibrated* probability layer on top of Open-Meteo ECMWF-AIFS, not a fake nowcast. The defensible technical claim is **"better-calibrated and lower frequency-bias than raw AIFS, while also beating Lagrangian persistence and climatology on a pre-registered walk-forward holdout"** — proven live on a public, recomputable scoreboard that no incumbent offers. The product moat is the **commute "leave-now" decision framing + transparent verification**, not raw forecast dynamics.

## 2. The Edge (only verification-SURVIVING claims)

- **Incumbents all force friction or abstraction.** mumbaiflood.in is a city-scale map + crowdsourced flood layer (no per-GPS verdict, no push, no API); IMD Mausam crashes and works at district/3-hour-window level; Skymet and AccuWeather are ad/paywall/notification-spam laden; Windy is an enthusiast map. **None gives a 2-second, single-spot, single-answer verdict.** This UX/time-to-answer gap is real and unowned. *(competitive-gaps: confirmed)*
- **AIFS has large, stationary, learnable biases at short range** — over-forecasts light rain (<1mm), under-forecasts heavy rain (FBI ≪1 above 10mm), over-smooths. These are exactly what a per-site calibration map corrects. *(ml-approach: high confidence)*
- **Calibration is where the cheap win lives, and a tiny model is competitive.** A data-driven logistic/Ridge + isotonic calibration ties/beats GBDT on Brier and exports to trivial JSON arithmetic. Post-processing turns raw AIFS into a *reliable* probability-of-rain. *(ml-approach: high)*
- **The "no incumbent publishes live skill vs the frontier model" gap is a marketing moat.** A transparent, recomputable scoreboard is itself the differentiator — credibility no bloated app offers. *(competitive + benchmark: confirmed)*

**Edge that did NOT survive — do not lean on it:** "We add genuine 0-2h *nowcasting skill* / beat AIFS dynamically." On the keyless Open-Meteo-only path there is **no radar** (where real 0-2h skill lives), **AIFS precip is only 6-hourly** (interpolated to 0-2h — beating it is near-circular), and **the only keyless "truth" is itself model-derived** (ERA5/best_match, with known Indian-monsoon biases). Real timing/placement skill is **not** achievable here. *(ml + competitive + benchmark: all confirmed the risk)*

## 3. Technical Plan Deltas

**Reframe the product in PLAN.md:** from "nowcast" to **"calibrated bias-correction of Open-Meteo AIFS"**. Headline metric is reliability, not RMSE.

**Best tiny-model family (confirmed):**
- Primary = **ordinal/multinomial logistic** (rain-class) **+ isotonic calibration**, OR per-class Ridge + isotonic. Exports as a handful of JSON coefficients → plain JS arithmetic on the browser path. ✅ respects "no local ML at serve time."
- Train **LightGBM/XGBoost offline only**, as an upper-bound sanity check — never ship it (GBDT scores are overconfident without calibration anyway).
- Add **quantile-mapping / frequency-bias correction** on top to explicitly fix AIFS's <1mm over-forecast and >10mm under-forecast.

**Feature set, ranked by confirmed importance:**
1. **Recent persistence** — latest Open-Meteo precip rate + 15/30/60-min trend (the single strongest 0-2h signal).
2. AIFS's own convective + large-scale precip, CAPE, precip-probability.
3. **Hour-of-day** (diurnal convection, sin/cos).
4. **Monsoon-phase / day-of-year.**
5. **best_match-vs-AIFS disagreement** as an uncertainty feature.
- **Skip** wind and far-field cells for a single-point forecast (confirmed low value).
- Keep **analog/k-NN only as a complementary feature**, never primary (fails on the wet extremes that matter most in Mumbai).

**Best FREE label source — the decisive correction:**
- **Do NOT** label against Open-Meteo's own ERA5/Historical-Forecast "observed" — it is model-derived and creates a closed loop that inflates skill 15-45% (confirmed). Using it alone caps you at a calibration-only claim.
- **DO** ingest an **independent ground truth on the GitHub Actions training path only** (keys are *allowed* there — only the live browser path must be keyless). Best free options, in order:
  1. **GPM IMERG** (satellite QPE, free, programmatic, global) — best automatable independent truth.
  2. **IMD AWS / station rainfall** for Mumbai (free, but coarser cadence/access).
  3. **In-app "is it raining now?" user taps** as a cheap crowd-truth channel for a validation subset.
- This single change is what upgrades the claim from "better calibrated" to a *potentially* defensible skill claim, and breaks the circularity trap.

**Validation method (confirmed mandatory):**
- **Walk-forward / expanding-origin** with a **≥2h purge gap** between train cutoff and test window. **Never** random k-fold (autocorrelation → silent overfit in the daily-retrain loop).

## 4. The Honest Benchmark

**The exact defensible public claim:**
> "On a pre-registered, walk-forward Mumbai holdout, our model beats **Lagrangian persistence AND climatology AND raw ECMWF-AIFS** at 0-2h, with bootstrapped skill-score CIs excluding zero — and is **better-calibrated** (reliability) and **lower frequency-bias** than raw AIFS. Heavy-rain claims are gated behind one full monsoon of independent-truth events."

**Pre-register ONE primary metric** before any retrain ships (kills cherry-picking): **CSI at "any rain ≥0.2mm/15min"** OR **Brier Skill Score vs Mumbai climatology**. Everything else is secondary reporting.

**Metric grid (per lead time 15/30/60/90/120 min × per threshold any/moderate/heavy):**
- Categorical: POD, FAR, **CSI**, frequency Bias, plus equitable **ETS/HSS** (fair across dry vs peak-monsoon).
- Probabilistic: **Brier + BSS vs climatology**, **reliability diagram + sharpness histogram**, ROC/AUC.
- **Wilson/Clopper-Pearson CIs** on POD/FAR/CSI; **paired bootstrap over event-DAYS** (not hours) on BSS.

**Promotion gate (significance, not point estimate):** promote only if candidate beats **champion AND raw AIFS AND persistence AND climatology** with paired-bootstrap CI excluding zero on the walk-forward holdout. Gray out any heavy-rain threshold until it has dozens of independent positive events (≥1 full monsoon).

**Scoreboard design:** live static charts rebuilt by the same hourly GitHub Actions cron — per-lead-time/per-threshold grid, rolling skill-vs-baselines time series, reliability diagram. **Publish the raw forecast-vs-observed log (CSV/Parquet in the repo)** so anyone can recompute every number. This is the strongest honesty signal and costs $0.

## 5. Product & Distribution Moves (ranked, free-to-build)

1. **Zero-friction single-spot verdict page.** Auto-GPS on load → Open-Meteo CORS no-key → ONE plain line: *"Dry for the next 2h"* / *"Rain ~in 40 min, ~1h — leave now."* No app, no login, no ads. Beats every incumbent on time-to-answer.
2. **"Leave-now" commute framing.** Combine 2h onset estimate + user's commute duration → *"Leave in the next 15 min to stay dry."* A decision, not a forecast. Pure browser arithmetic.
3. **Commute/waterlogging hook + programmatic SEO.** Generate ~150 static `<area>/<station> rain now` pages (Andheri subway, Hindmata, Kurla, Sakinaka, Dadar, Bandra, Powai, Thane), auto-refreshing from Open-Meteo, hub-linked area↔line↔station. **Index weeks before monsoon onset.** Owns the long-tail "rain in <locality> mumbai right now."
4. **Share-card as the product surface.** One-tap *"🌧️ Rain in ~20 min at Bandra — leave now"* og-card with a **wa.me prefilled-message** button + X-intent link. Every alert is pre-built to drop into housing-society/neighbourhood WhatsApp groups; deep-links back to the locality page (viral loop + SEO backlinks).
5. **Public "we beat the baselines" scoreboard** (§4) doubles as a PR/credibility hook — journalists and r/mumbai love "indie dev's transparent model."
6. **Best-effort push, correctly architected.** Run the **per-minute alert eval + send on a Cloudflare Worker cron** (minute granularity, free tier, KV for subs, pushforge/@mmmike/web-push) — **NOT** GitHub Actions (15-60 min drift, 5-min floor). Keep retrain/promote on Actions. VAPID keys live only on the edge sender.
7. **Design around the iOS wall, don't fight it.** Push is best-effort only (iOS needs manual Add-to-Home-Screen, ~70-85% delivery, vanishing subs). Lead with the **on-page live nowcast** as the primary surface; offer a no-install fallback (self-refreshing page + optional Telegram/X alert path).
8. **Society/group mode + #MumbaiRains seeding.** One shareable group link auto-posts the leave-now card; post auto-generated per-storm graphics into the existing meme cycle for free reach.

## 6. Monetization Path to $1k/mo

**⚠️ Hard constraint collision (confirmed twice in verification):** Open-Meteo's **free tier is non-commercial** — it bars sites with **ads or subscriptions**. Monetizing on the free keyless tier **violates its Terms** and breaks "$0 at scale." This must be designed for explicitly.

**Most realistic route, in order:**
1. **Decouple money from the free data tier.** Keep the public hyperlocal page on free Open-Meteo (non-commercial, attribution-compliant), and put revenue behind a **separate, clearly-commercial product** powered by a **paid Open-Meteo API key (server-side only)** — e.g. a **B2B "Mumbai rain/waterlogging alerts API + dashboard"** for logistics/delivery fleets, housing societies, event organizers, schools, and local businesses. Paid API cost is tiny vs ₹/$ B2B pricing; this is the single cleanest path to $1k/mo without touching the consumer page's $0 economics.
2. **Sponsorship/civic grant** of the public scoreboard ("Mumbai monsoon accuracy index, sponsored by …") — keeps the consumer surface ad-light and grant-funded rather than ad-funded.
3. **Donations/Buy-Me-a-Coffee + Pro tier** (more saved spots, longer history, priority alerts) — only on the paid-key commercial product, never on the free-tier page.

Honest note: the consumer free page is a **funnel and credibility engine**, not the revenue source. Revenue comes from B2B/commercial use under a paid key.

## 7. Top 5 Risks & Neutralization

1. **Circular ground truth → fake skill (the #1 confirmed risk).** *Neutralize:* ingest GPM IMERG / IMD station data as **independent truth on the Actions training path only**; until then, restrict the public claim to **calibration/reliability**, which the holdout proves regardless of truth purity.
2. **"Beats AIFS at 0-2h" is true-but-meaningless** (no NWP spin-up skill; AIFS is 6-hourly).  *Neutralize:* make **persistence + climatology** first-class baselines and the *real* bar; advertise AIFS-beating only as a footnote.
3. **Push is mistimed/unreliable** (Actions cron drift; iOS install wall, ~70-85% delivery).  *Neutralize:* alert send on **Cloudflare Worker cron**; treat push as best-effort; **lead with on-page live nowcast**, not push.
4. **Monetization violates Open-Meteo free-tier Terms.**  *Neutralize:* free page stays non-commercial + attributed; revenue lives on a **separate paid-key server-side B2B product** (§6).
5. **Heavy-rain claims unstable on small samples.**  *Neutralize:* Wilson/Clopper-Pearson + bootstrap CIs on every number; **gate heavy-rain claims behind one full monsoon** of independent positive events; gray out until CI excludes the baseline.

Secondary infra risk: GitHub Actions schedules **auto-disable after 60 days idle** and drift at top-of-hour → add a keep-alive commit + monitor the logging cron's freshness.

## 8. Reality Check — What NOT to Claim / Where Incumbents Stay Ahead

- **Do NOT claim genuine 0-2h nowcasting skill, sharp minute-level timing, or "we beat the frontier model dynamically."** Real sub-1h skill needs radar/optical-flow the project cannot access keylessly. Convective timing at 0-2h is intrinsically low-predictability (double-penalty problem).
- **Do NOT headline "beats ECMWF-AIFS."** It's near-circular on the keyless path; lead with calibration + beating persistence/climatology instead.
- **Where mumbaiflood.in stays ahead:** actual **flood/waterlogging prediction** (GFS→CNN + radar ConvLSTM + HAND + 9 water-level stations + crowdsourcing). We can surface *rain*, not a validated *per-spot flood depth*. Don't claim flood prediction without that data.
- **Where IMD stays ahead:** official **warnings/authority** and station network. We complement, not replace, official alerts.
- **Where AccuWeather MinuteCast stays ahead:** genuine **minute-by-minute precip start/stop** UX maturity (even if ad-laden). Match the *framing*, not a claim of superior raw timing.
- **Honest public posture:** "Fastest, cleanest, best-*calibrated* single-spot Mumbai rain check, with transparent live accuracy — not a magic nowcast." That claim survives verification; anything stronger does not.