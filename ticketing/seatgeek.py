"""
SeatGeek Platform API client — comedy events.

Docs: https://platform.seatgeek.com/
Requires: SEATGEEK_CLIENT_ID env var
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from utils.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.seatgeek.com/2/events"
PAGE_SIZE = 500


class SeatGeekClient:
    def __init__(self):
        self._client_id = os.environ["SEATGEEK_CLIENT_ID"]
        self._client_secret = os.environ.get("SEATGEEK_CLIENT_SECRET", "")
        self._client = httpx.Client(timeout=30)

    def fetch_nyc_comedy(self, days_ahead: int = 90) -> list[dict]:
        """Return all upcoming NYC comedy events within the next `days_ahead` days."""
        now = datetime.now(tz=timezone.utc)
        start = now.strftime("%Y-%m-%dT%H:%M:%S")
        end = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%S")

        all_events: list[dict] = []
        page = 1
        while True:
            data = self._fetch_page(page, start, end)
            events = data.get("events", [])
            all_events.extend(events)

            meta = data.get("meta", {})
            total = meta.get("total", 0)
            if len(all_events) >= total or not events or len(all_events) >= 5000:
                break
            page += 1

        logger.info(f"SeatGeek: fetched {len(all_events)} comedy events")
        return all_events

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=10),
    )
    def _fetch_page(self, page: int, start: str, end: str) -> dict:
        params: dict = {
            "client_id": self._client_id,
            "type": "comedy",
            "venue.state": "NY",
            "venue.city": "New York",
            "datetime_local.gte": start,
            "datetime_local.lte": end,
            "per_page": PAGE_SIZE,
            "page": page,
            "sort": "datetime_local.asc",
        }
        if self._client_secret:
            params["client_secret"] = self._client_secret

        resp = self._client.get(BASE_URL, params=params)
        resp.raise_for_status()
        logger.debug(f"SeatGeek page {page}: HTTP {resp.status_code}")
        return resp.json()

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
