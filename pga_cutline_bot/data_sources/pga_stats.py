"""PGA Tour statistics data source.

PGA Tour does not publish a public, documented REST API. Its website
(pgatour.com) is backed by an internal GraphQL endpoint
(``orchestrator.pgatour.com/graphql``) that changes shape without notice and
is not intended for third-party use. This client is written against that
endpoint's known query shapes so it can be pointed at a real season once the
runtime has outbound network access, but it degrades gracefully:

1. If ``config.DEMO_MODE`` is set (the default in this sandbox, since
   outbound access to pgatour.com is blocked here), it loads the bundled
   synthetic fixtures in ``sample_data/`` instead.
2. If a live call fails for any reason (network, schema drift, rate limit),
   it logs a warning and falls back to the same fixtures rather than
   crashing the pipeline.

Swap in a licensed data vendor (e.g. Data Golf, SportsDataIO) by
implementing the same ``fetch_field`` / ``fetch_player_stats`` interface.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from pga_cutline_bot import config
from pga_cutline_bot.models import PlayerStats, PlayingStatus

logger = logging.getLogger(__name__)

SAMPLE_DATA_PATH = Path(__file__).resolve().parent.parent / "sample_data" / "pga_stats_sample.json"

# Known (subject-to-change) GraphQL query used by pgatour.com to render a
# tournament's field + player profile stats page. Kept here for reference /
# future live wiring rather than executed against in this sandbox.
FIELD_QUERY = """
query TournamentField($tourCode: String!, $tournamentId: String!) {
  field(tourCode: $tourCode, id: $tournamentId) {
    players { id firstName lastName status statusNote }
  }
}
"""

PLAYER_STATS_QUERY = """
query PlayerStats($playerId: String!, $statIds: [String!]!) {
  playerStats(playerId: $playerId, statIds: $statIds) { statId value }
}
"""


class PGATourStatsClient:
    def __init__(self, base_url: str = config.PGA_TOUR_STATS_BASE_URL, demo_mode: bool = config.DEMO_MODE):
        self.base_url = base_url
        self.demo_mode = demo_mode

    def fetch_field(self, tournament_slug: str) -> list[PlayerStats]:
        """Return PlayerStats for every player confirmed in the tournament field."""
        if self.demo_mode:
            return self._load_sample_field()
        try:
            return self._fetch_field_live(tournament_slug)
        except Exception as exc:  # network, schema drift, throttling, etc.
            logger.warning(
                "Live PGA Tour field fetch failed (%s); falling back to sample data.", exc
            )
            return self._load_sample_field()

    def _fetch_field_live(self, tournament_slug: str) -> list[PlayerStats]:
        import requests  # local import: optional dependency, only needed live

        resp = requests.post(
            self.base_url,
            json={
                "query": FIELD_QUERY,
                "variables": {"tourCode": "R", "tournamentId": tournament_slug},
            },
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        players_raw = payload["data"]["field"]["players"]

        stats: list[PlayerStats] = []
        for p in players_raw:
            player_id = p["id"]
            per_player_stats = self._fetch_player_stat_block_live(player_id)
            stats.append(
                self._build_player_stats(
                    player_id=player_id,
                    name=f"{p['firstName']} {p['lastName']}",
                    status=self._parse_status(p.get("status")),
                    status_note=p.get("statusNote") or "",
                    raw_stats=per_player_stats,
                )
            )
        return stats

    def _fetch_player_stat_block_live(self, player_id: str) -> dict:
        import requests

        stat_ids = [
            "scoring_avg_last10",
            "scoring_avg_last4",
            "scoring_avg_ytd",
            "cut_pct_career",
            "cut_pct_last_season",
            "cut_pct_last_12mo",
            "sg_total_recent",
        ]
        resp = requests.post(
            self.base_url,
            json={
                "query": PLAYER_STATS_QUERY,
                "variables": {"playerId": player_id, "statIds": stat_ids},
            },
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        rows = resp.json()["data"]["playerStats"]
        return {row["statId"]: row["value"] for row in rows}

    @staticmethod
    def _parse_status(raw: Optional[str]) -> PlayingStatus:
        mapping = {
            "ACTIVE": PlayingStatus.CONFIRMED,
            "CONFIRMED": PlayingStatus.CONFIRMED,
            "QUESTIONABLE": PlayingStatus.QUESTIONABLE,
            "WD": PlayingStatus.WITHDRAWN,
            "WITHDRAWN": PlayingStatus.WITHDRAWN,
        }
        return mapping.get((raw or "").upper(), PlayingStatus.UNKNOWN)

    @staticmethod
    def _build_player_stats(player_id: str, name: str, status: PlayingStatus, status_note: str, raw_stats: dict) -> PlayerStats:
        return PlayerStats(
            player_id=player_id,
            name=name,
            scoring_avg_last10=float(raw_stats.get("scoring_avg_last10", 71.5)),
            scoring_avg_last4weeks=float(raw_stats.get("scoring_avg_last4", 71.5)),
            scoring_avg_ytd=float(raw_stats.get("scoring_avg_ytd", 71.5)),
            cut_pct_career=float(raw_stats.get("cut_pct_career", 0.6)),
            cut_pct_last_season=float(raw_stats.get("cut_pct_last_season", 0.6)),
            cut_pct_last_12mo=float(raw_stats.get("cut_pct_last_12mo", 0.6)),
            sg_total_recent=float(raw_stats.get("sg_total_recent", 0.0)),
            sg_by_course_type={},
            recent_finishes=[],
            status=status,
            status_note=status_note,
        )

    def _load_sample_field(self) -> list[PlayerStats]:
        with open(SAMPLE_DATA_PATH) as f:
            raw = json.load(f)
        players = []
        for p in raw["players"]:
            players.append(
                PlayerStats(
                    player_id=p["player_id"],
                    name=p["name"],
                    scoring_avg_last10=p["scoring_avg_last10"],
                    scoring_avg_last4weeks=p["scoring_avg_last4weeks"],
                    scoring_avg_ytd=p["scoring_avg_ytd"],
                    cut_pct_career=p["cut_pct_career"],
                    cut_pct_last_season=p["cut_pct_last_season"],
                    cut_pct_last_12mo=p["cut_pct_last_12mo"],
                    sg_total_recent=p["sg_total_recent"],
                    sg_by_course_type=p["sg_by_course_type"],
                    recent_finishes=p["recent_finishes"],
                    course_history_rounds=p.get("course_history_rounds", 0),
                    course_history_cut_pct=p.get("course_history_cut_pct"),
                    status=PlayingStatus(p.get("status", "confirmed")),
                    status_note=p.get("status_note", ""),
                )
            )
        return players
