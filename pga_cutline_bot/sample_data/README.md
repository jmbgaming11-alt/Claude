# Sample data (synthetic — not real players, stats, or odds)

This directory is a **fixture set for demo/testing only**. Outbound network
access to `pgatour.com` and `api.elections.kalshi.com` is blocked in the
sandbox this project was built in, so none of this repo's example output
reflects real players, real PGA Tour statistics, or real Kalshi market
prices for the Rocket Classic or any other event.

- `pga_stats_sample.json` — 14 fictional players with made-up scoring
  averages, cut percentages, strokes-gained figures, and course history.
  Player names (e.g. "Alex Rivermoor") were invented for this fixture and do
  not refer to real golfers.
- `kalshi_markets_sample.json` — matching fictional "makes the cut" markets
  with made-up bid/ask prices, shaped like real Kalshi market objects
  (ticker, yes_bid, yes_ask, no_bid, no_ask, volume) so the pipeline code
  exercises the same parsing path it would use against the live API.
- `ledger.jsonl` — generated at runtime by `tracking/ledger.py` when you run
  the CLI; not checked in with pre-populated fake history.

To run against reality:

1. Point `PGATourStatsClient` at a licensed stats vendor (Data Golf,
   SportsDataIO, or a PGA Tour data agreement) — the public site has no
   documented API, so `pga_stats.py`'s live path is a best-effort sketch of
   its internal GraphQL shape, not a stable integration.
2. Set `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH` to a real Kalshi
   API key/private key pair, and `PGA_BOT_DEMO_MODE=0`.
3. Run from an environment with outbound HTTPS access to both hosts.
