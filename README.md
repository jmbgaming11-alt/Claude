# PGA Tour Cut-Line Betting Algorithm

Identifies +EV "makes the cut" bets on Kalshi by comparing a weighted
statistical model of each player's cut probability against Kalshi's
market-implied probability, then allocates a fixed weekly budget across
straight bets and parlays.

**Important — read before using with real money:**
- This sandbox has **no outbound network access** to `pgatour.com` or
  `api.elections.kalshi.com` (confirmed: both return `403` at the proxy
  gateway). Every result you get by running this repo as-is comes from the
  synthetic, clearly-labeled fixtures in `pga_cutline_bot/sample_data/` —
  **not** real players, stats, or odds. See
  `pga_cutline_bot/sample_data/README.md`.
- Kalshi markets are real-money financial instruments. Nothing here is
  financial advice; the model's weights are a reasonable starting point,
  not a validated/backtested edge. Past accuracy of any model is not a
  guarantee of future results, and prediction markets can and do move
  against you.
- Before wiring in real credentials, read Kalshi's terms of service and
  API rate limits, and confirm your jurisdiction permits this activity.

## What it does

1. **Data collection** (`data_sources/`)
   - `pga_stats.py` — fetches the tournament field and each player's
     scoring averages, cut percentages, strokes-gained-by-course-type, and
     course history. Live path targets the (undocumented, subject to
     change) GraphQL endpoint behind pgatour.com; falls back to
     `sample_data/pga_stats_sample.json` if that fails or `DEMO_MODE` is on.
   - `kalshi_client.py` — real Kalshi API v2 client with RSA-PSS request
     signing (the auth scheme Kalshi's private endpoints require). Falls
     back to `sample_data/kalshi_markets_sample.json` in demo mode.
2. **Probability model** (`model/probability_model.py`) — Step 1 of the
   spec: a weighted blend of strokes gained (40%), historical cut % (30%),
   last-4-weeks form trend (20%), and course-specific history (10%), each
   squashed through a logistic function so the blend stays a valid
   probability without requiring a fitted regression.
3. **EV comparison** (`model/ev.py`) — Step 2: matches predictions to
   markets by normalized player name, computes edge (model prob − market
   implied prob) and expected value per dollar staked, and filters to
   `min_edge` (default 5%).
4. **Allocation** (`allocation/`) — Step 3: fractional-Kelly-sized straight
   bets on the top +EV players, plus 2–3 leg parlays built from the
   remaining pool, preferring legs whose predictions are driven by
   *different* dominant factors (SG vs. form vs. course history) as a
   simple proxy for less-correlated outcomes. Budget is split
   straights/parlays (default 65/35) and every bet is capped at
   `max_single_bet_fraction` of the weekly budget.
5. **Reporting & tracking** (`reporting/`, `tracking/`) — Step 4: prints a
   betting slip with reasoning, optionally writes a CSV, and appends every
   recommendation to a JSON-lines ledger (`sample_data/ledger.jsonl`,
   git-ignored) for later ROI tracking once results are known.

## Running it

```bash
pip install -r requirements.txt
python3 -m pga_cutline_bot.cli                       # demo mode, $50 budget
python3 -m pga_cutline_bot.cli --budget 100 --min-edge 0.03
python3 -m pga_cutline_bot.cli --csv slip.csv         # also write a CSV
python3 -m pga_cutline_bot.cli --show-roi             # cumulative ledger ROI
python3 -m pytest tests/ -q                           # unit tests
```

### Going live

1. Get a real stats source: `pga_stats.py`'s live path is a best-effort
   sketch of pgatour.com's internal API and **will need adjustment** — PGA
   Tour has no public/documented API. Consider a licensed vendor (Data
   Golf, SportsDataIO) instead; swap it in behind the same
   `fetch_field(tournament_slug) -> list[PlayerStats]` interface.
2. Create a Kalshi API key and download its private key, then set:
   ```bash
   export KALSHI_API_KEY_ID=...
   export KALSHI_PRIVATE_KEY_PATH=/path/to/key.pem
   export PGA_BOT_DEMO_MODE=0
   ```
3. Run from an environment with outbound HTTPS access to both hosts, and
   set `config.DEFAULT_TOURNAMENT` (or pass a custom `Tournament`) to the
   correct `pga_tour_slug` / `kalshi_series_ticker` for the week.
4. This project does not place orders — it only produces recommendations.
   Placing real orders against `KalshiClient` would require adding a
   signed `POST /portfolio/orders` call and, given real money is on the
   line, a human should confirm each bet before it's submitted.

## Project layout

```
pga_cutline_bot/
  config.py                 weights, budget/risk knobs, env-driven credentials
  models.py                  shared dataclasses (PlayerStats, KalshiMarket, ...)
  data_sources/
    pga_stats.py             PGA Tour field + stats (live sketch + sample fallback)
    kalshi_client.py         Kalshi v2 REST client with RSA-PSS signing
  model/
    probability_model.py     Step 1: weighted cut-probability model
    ev.py                    Step 2: model-vs-market matching, edge, EV
  allocation/
    kelly.py                 fractional Kelly sizing
    allocator.py              Step 3: straight bet + parlay construction, budget split
  reporting/
    slip.py                  Step 4: console + CSV betting slip
  tracking/
    ledger.py                prediction/outcome log + ROI summary
  pipeline.py                orchestrates the full run
  cli.py                     `python -m pga_cutline_bot.cli`
  sample_data/               synthetic fixtures (see its own README)
tests/                       pytest unit tests for model, EV, and allocator
```

## Known limitations

- Cut-making outcomes are treated as independent across parlay legs. In
  reality, weather/course-setup shifts (e.g., a hard, windy afternoon wave)
  create some positive correlation between players in the same tee wave,
  which would make parlay EV slightly optimistic. Not modeled here.
- The probability model is a hand-weighted logistic blend, not a fitted
  regression — the spec's Step 1 weights (40/30/20/10) are used directly
  rather than learned from historical outcomes. `tracking/ledger.py` exists
  so real outcomes can be logged and used to fit/calibrate weights later.
- Player-name matching between the stats source and Kalshi market titles is
  a normalized-string exact match; a real deployment should also handle
  suffixes (Jr./III), accented characters, and Kalshi ticker/title format
  changes.
