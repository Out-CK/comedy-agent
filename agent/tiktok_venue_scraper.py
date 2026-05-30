"""
ComedyTikTokVenueScraper — scrapes a curated list of NYC comedy venue and comedian TikTok accounts.
"""
from __future__ import annotations

import asyncio
from typing import Any

from tools.nimble_tiktok_tool import NimbleTikTokAccountTool
from utils.logger import get_logger

logger = get_logger(__name__)

CONCURRENCY_LIMIT = 4

NYC_COMEDY_TIKTOK_ACCOUNTS = [
    # Comedy clubs / venues
    "comedycellar",
    "standupny",
    "gothamcomedyclub",
    "carolinesonbroadway",
    "ucbcomedy",
    "thepitnyc",
    "thestandnyc",
    "eastvillecomedyclub",
    # Comedy media / aggregators
    "timeout.newyork",
    "nycgo",
    "vulture",
    "comedycentral",
    # Individual comedians who frequently perform in NYC
    "jerryseinfeld",
    "amyschumer",
    "jimgaffigan",
    "johnmulaney",
    "trevornoah",
    "conanobrien",
    "chrisrock",
    "davidchappelle",
    "hannahgadsby",
    "nickofferman",
    "natebargatze",
    "garyshandling",
    "mikobirbiglia",
]

NYC_COMEDY_TIKTOK_ACCOUNTS = list(dict.fromkeys(NYC_COMEDY_TIKTOK_ACCOUNTS))


class ComedyTikTokVenueScraper:
    def __init__(self):
        self._account_tool = NimbleTikTokAccountTool()

    def scrape(self) -> list[dict[str, Any]]:
        logger.info(
            f"ComedyTikTokVenueScraper: scraping {len(NYC_COMEDY_TIKTOK_ACCOUNTS)} accounts"
        )
        results = asyncio.run(self._scrape_all_concurrent())
        logger.info(f"ComedyTikTokVenueScraper: collected {len(results)} posts total")
        return results

    async def _scrape_all_concurrent(self) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        async def scrape_one(handle: str) -> list[dict[str, Any]]:
            async with semaphore:
                loop = asyncio.get_event_loop()
                try:
                    data = await loop.run_in_executor(
                        None, lambda: self._account_tool._run(handle)
                    )
                    return self._normalize_posts(handle, data)
                except Exception as e:
                    logger.error(f"TikTok account scrape failed for @{handle}: {e}")
                    return []

        tasks = [scrape_one(h) for h in NYC_COMEDY_TIKTOK_ACCOUNTS]
        results_nested = await asyncio.gather(*tasks)
        return [item for sublist in results_nested for item in sublist]

    @staticmethod
    def _normalize_posts(handle: str, data: dict[str, Any]) -> list[dict[str, Any]]:
        posts = data.get("top_posts_data") or []
        records = []
        for post in posts:
            post_id = post.get("post_id") or ""
            description = post.get("description") or ""
            post_url = post.get("post_url") or (
                f"https://www.tiktok.com/@{handle}/video/{post_id}" if post_id else ""
            )
            records.append({
                "post_id": post_id,
                "caption": description,
                "description": description,
                "creator_handle": handle,
                "posted_at": post.get("create_date") or "",
                "source_tag": f"venue_account:{handle}",
                "tiktok_url": post_url,
            })
        return records
