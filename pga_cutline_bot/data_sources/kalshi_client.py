"""Kalshi REST API v2 client, scoped to "make the cut" markets.

Kalshi's authenticated endpoints require request signing: each request
carries ``KALSHI-ACCESS-KEY``, ``KALSHI-ACCESS-TIMESTAMP``, and
``KALSHI-ACCESS-SIGNATURE`` headers, where the signature is an RSA-PSS
(SHA-256, MGF1) signature over ``timestamp + method + path`` using the
private key associated with your API key ID. Market *read* endpoints
(``GET /markets``, ``GET /series``) are public and don't strictly require
auth, but signing every request is simplest and works for both public and
private endpoints alike.

Credentials are read from the environment (see config.py):
  - ``KALSHI_API_KEY_ID``: the API key ID from your Kalshi account.
  - ``KALSHI_PRIVATE_KEY_PATH``: path to the PEM-encoded RSA private key
    downloaded when the key was created.

If those aren't set, or ``config.DEMO_MODE`` is on (the default here, since
this sandbox has no outbound access to kalshi.com), the client serves the
bundled synthetic fixtures instead of calling the network.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path

from pga_cutline_bot import config
from pga_cutline_bot.models import KalshiMarket

logger = logging.getLogger(__name__)

SAMPLE_DATA_PATH = Path(__file__).resolve().parent.parent / "sample_data" / "kalshi_markets_sample.json"


class KalshiAuthError(RuntimeError):
    pass


class KalshiClient:
    def __init__(
        self,
        base_url: str = config.KALSHI_BASE_URL,
        api_key_id: str = config.KALSHI_API_KEY_ID,
        private_key_path: str = config.KALSHI_PRIVATE_KEY_PATH,
        demo_mode: bool = config.DEMO_MODE,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key_id = api_key_id
        self.private_key_path = private_key_path
        self.demo_mode = demo_mode
        self._private_key = None  # lazily loaded, live mode only

    def get_cut_markets(self, series_ticker: str) -> list[KalshiMarket]:
        """Return every 'Player X makes the cut' market in a series (tournament)."""
        if self.demo_mode:
            return self._load_sample_markets()
        try:
            return self._get_cut_markets_live(series_ticker)
        except Exception as exc:
            logger.warning(
                "Live Kalshi market fetch failed (%s); falling back to sample data.", exc
            )
            return self._load_sample_markets()

    # -- Live implementation -------------------------------------------------

    def _get_cut_markets_live(self, series_ticker: str) -> list[KalshiMarket]:
        import requests

        path = "/markets"
        params = {"series_ticker": series_ticker, "status": "open", "limit": 200}
        resp = self._signed_request("GET", path, params=params)
        markets_raw = resp.json().get("markets", [])

        markets = []
        for m in markets_raw:
            markets.append(
                KalshiMarket(
                    ticker=m["ticker"],
                    player_name=self._player_name_from_title(m.get("title", m["ticker"])),
                    yes_bid=float(m.get("yes_bid", 0)),
                    yes_ask=float(m.get("yes_ask", 100)),
                    no_bid=float(m.get("no_bid", 0)),
                    no_ask=float(m.get("no_ask", 100)),
                    volume=int(m.get("volume", 0)),
                )
            )
        return markets

    @staticmethod
    def _player_name_from_title(title: str) -> str:
        # Kalshi market titles for this series are formatted like
        # "Will <Player Name> make the cut at the <Tournament>?"
        if " make the cut" in title:
            return title.split("Will ", 1)[-1].split(" make the cut")[0].strip()
        return title

    def _signed_request(self, method: str, path: str, params: dict | None = None):
        import requests

        if not self.api_key_id or not self.private_key_path:
            raise KalshiAuthError(
                "KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH must be set for live requests."
            )

        timestamp_ms = str(int(time.time() * 1000))
        full_path = f"/trade-api/v2{path}"
        signature = self._sign(timestamp_ms + method.upper() + full_path)

        headers = {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}{path}"
        resp = requests.request(method, url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp

    def _sign(self, message: str) -> str:
        # Imported lazily so `cryptography` is only required for live trading,
        # not for running the demo/sample-data pipeline.
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        if self._private_key is None:
            with open(self.private_key_path, "rb") as f:
                self._private_key = load_pem_private_key(f.read(), password=None)

        signature = self._private_key.sign(
            message.encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    # -- Demo / fallback ------------------------------------------------------

    def _load_sample_markets(self) -> list[KalshiMarket]:
        with open(SAMPLE_DATA_PATH) as f:
            raw = json.load(f)
        return [
            KalshiMarket(
                ticker=m["ticker"],
                player_name=m["player_name"],
                yes_bid=m["yes_bid"],
                yes_ask=m["yes_ask"],
                no_bid=m["no_bid"],
                no_ask=m["no_ask"],
                volume=m.get("volume", 0),
            )
            for m in raw["markets"]
        ]
