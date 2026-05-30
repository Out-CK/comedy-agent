"""
ComedyInstagramAgent — discovers upcoming NYC comedy shows via curated Instagram profiles
and inserts them into the Supabase event_entry_database.

Pipeline:
  1. Scrape curated NYC comedy venue/comedian Instagram profiles via Nimble.
  2. Store raw post content in event_web_database.
  3. Parse post captions into EventEntry objects with Claude.
  4. Enrich entries with venue coords.
  5. Intra-batch deduplication.
  6. Cross-DB deduplication.
  7. Insert new entries into event_entry_database.
  8. Archive past events.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime

from agent.duplicate_finder import DuplicateFinder
from agent.instagram_post_parser import InstagramPostParser
from agent.past_event_archiver import PastEventArchiver
from agent.web_batch_parser import EventEntry
from db.operations import (
    get_existing_venue_coords,
    insert_event_entries,
    insert_web_batch,
)
from db.supabase_client import get_supabase_client
from tools.nimble_instagram_tool import NimbleInstagramProfileTool
from utils.geocoder import enrich_entries_with_coords
from utils.id_generator import IDGenerator
from utils.logger import get_logger

logger = get_logger(__name__)

CONCURRENCY_LIMIT = 4

# Curated NYC comedy venue, club, and comedian Instagram handles
NYC_COMEDY_INSTAGRAM_ACCOUNTS = [
    # Comedy clubs / venues
    "comedycellar",
    "standupny",
    "gothamcomedyclub",
    "broadwaycomedyclub",
    "carolinesonbroadway",
    "newyorkcomedyclub",
    "eastvillecomedyclub",
    "thestandnyc",
    "creekandthecave",
    "ucbcomedy",
    "thepitnyc",
    "qedcomedy",
    "dangerfieldsnyc",
    "comicstriplive",
    "unionhallny",
    "thebellhouseny",
    "houseofyes",       # alternative comedy nights
    "publicrecordsnyc", # occasional comedy
    # NYC comedy aggregators / media
    "nyccomedyfestival",
    "timeout.newyork",
    "nycgo",
    "vulture",
    "newyorkermag",
    # Individual comedians with frequent NYC shows
    "jerryseinfeld",
    "chrisrock",
    "amyschumer",
    "trevornoah",
    "jimgaffigan",
    "conanobrien",
    "sethmeyers",
    "johnmulaney",
]

NYC_COMEDY_INSTAGRAM_ACCOUNTS = list(dict.fromkeys(NYC_COMEDY_INSTAGRAM_ACCOUNTS))


class ComedyInstagramAgent:
    def __init__(self):
        self._profile_tool = NimbleInstagramProfileTool()
        self._supabase = get_supabase_client()

    def run(self) -> None:
        run_start = time.time()
        entry_batch_id = datetime.now().strftime("%m%d%Y_%H%M%S") + "_ig"
        web_batch_id = datetime.now().strftime("%m%d%Y") + "_ig"
        logger.info(f"=== Comedy Instagram Run START | entry_batch_id={entry_batch_id} ===")

        stats = {
            "accounts_attempted": len(NYC_COMEDY_INSTAGRAM_ACCOUNTS),
            "profiles_scraped": 0,
            "posts_collected": 0,
            "entries_parsed": 0,
            "dupes_intrabatch": 0,
            "dupes_crossdb": 0,
            "entries_inserted": 0,
            "entries_archived": 0,
        }

        # Step 1 — Scrape Instagram profiles
        self._step_log("Step 1: Scrape Instagram Profiles")
        post_pages: list[dict] = []
        try:
            raw_profiles = asyncio.run(
                self._scrape_profiles_concurrent(NYC_COMEDY_INSTAGRAM_ACCOUNTS)
            )
            for handle, profile_data in raw_profiles:
                if not profile_data:
                    continue
                posts = profile_data.get("posts") or []
                bio = profile_data.get("biography") or ""
                profile_url = (
                    profile_data.get("profile_url")
                    or f"https://www.instagram.com/{handle}/"
                )
                if not posts:
                    logger.debug(f"@{handle}: no posts returned")
                    continue

                stats["profiles_scraped"] += 1
                combined_text = f"BIOGRAPHY: {bio}\n\n"
                for post in posts:
                    caption = self._extract_post_caption(post)
                    if caption:
                        combined_text += f"---\nPOST: {caption}\n"

                post_pages.append({
                    "url": profile_url,
                    "handle": handle,
                    "content": combined_text[:30000],
                })
                stats["posts_collected"] += len(posts)

            logger.info(
                f"Scraped {stats['profiles_scraped']}/{len(NYC_COMEDY_INSTAGRAM_ACCOUNTS)} profiles, "
                f"{stats['posts_collected']} posts total"
            )
        except Exception as e:
            logger.error(f"Step 1 failed: {e}")

        if not post_pages:
            logger.warning("No Instagram content retrieved — aborting Comedy Instagram Run")
            return

        # Step 2 — Store Raw Instagram Content
        self._step_log("Step 2: Store Raw Content")
        try:
            db_records = [
                {
                    "web_batch_id": web_batch_id,
                    "source_url": p["url"],
                    "query_used": "comedy_instagram_profile",
                    "round": 1,
                    "content": p["content"],
                }
                for p in post_pages
            ]
            insert_web_batch(db_records)
        except Exception as e:
            logger.error(f"Step 2 failed: {e}")

        # Step 3 — Parse Posts into Event Entries
        self._step_log("Step 3: Parse Instagram Posts")
        id_generator = IDGenerator(self._supabase)
        entry_batch: list[EventEntry] = []
        try:
            raw_entries = InstagramPostParser().parse(post_pages)
            stats["entries_parsed"] = len(raw_entries)
            for entry in raw_entries:
                entry.entry_batch_id = entry_batch_id
                entry.event_entry_id = id_generator.next()
                entry.event_type = "comedy"
            entry_batch = raw_entries
            logger.info(f"Parsed {len(entry_batch)} raw entries from Instagram")
        except Exception as e:
            logger.error(f"Step 3 failed: {e}")

        # Step 4 — Geocoding Enrichment
        self._step_log("Step 4: Geocoding Enrichment")
        try:
            known_coords = get_existing_venue_coords()
            entry_dicts = [e.model_dump() for e in entry_batch]
            entry_dicts = enrich_entries_with_coords(entry_dicts, known_coords)
            for entry, d in zip(entry_batch, entry_dicts):
                entry.address = d.get("address")
                entry.lat = d.get("lat")
                entry.lng = d.get("lng")
        except Exception as e:
            logger.error(f"Step 4 failed: {e}")

        # Step 5 — Intra-Batch Deduplication
        self._step_log("Step 5: Intra-Batch Deduplication")
        dup_finder = DuplicateFinder(id_generator)
        try:
            pre_count = len(entry_batch)
            entry_batch = dup_finder.deduplicate_batch(entry_batch)
            stats["dupes_intrabatch"] = pre_count - len(entry_batch)
        except Exception as e:
            logger.error(f"Step 5 failed: {e}")

        # Step 6 — Cross-DB Deduplication
        self._step_log("Step 6: Cross-DB Deduplication")
        try:
            pre_count = len(entry_batch)
            entry_batch = dup_finder.cross_reference_db(entry_batch)
            stats["dupes_crossdb"] = pre_count - len(entry_batch)
        except Exception as e:
            logger.error(f"Step 6 failed: {e}")

        # Step 7 — Insert Event Entries
        self._step_log("Step 7: Insert Event Entries")
        try:
            rows = [e.model_dump() for e in entry_batch]
            stats["entries_inserted"] = insert_event_entries(rows)
        except Exception as e:
            logger.error(f"Step 7 failed: {e}")

        # Step 8 — Archive Past Events
        self._step_log("Step 8: Archive Past Events")
        try:
            stats["entries_archived"] = PastEventArchiver().run()
        except Exception as e:
            logger.error(f"Step 8 failed: {e}")

        duration = time.time() - run_start
        logger.info(
            f"=== Comedy Instagram Run COMPLETE | entry_batch_id={entry_batch_id} | "
            f"duration={duration:.1f}s ===\n"
            f"  Accounts attempted:        {stats['accounts_attempted']}\n"
            f"  Profiles scraped:          {stats['profiles_scraped']}\n"
            f"  Posts collected:           {stats['posts_collected']}\n"
            f"  Raw entries parsed:        {stats['entries_parsed']}\n"
            f"  Intra-batch dupes removed: {stats['dupes_intrabatch']}\n"
            f"  Cross-DB dupes removed:    {stats['dupes_crossdb']}\n"
            f"  New entries inserted:      {stats['entries_inserted']}\n"
            f"  Entries archived:          {stats['entries_archived']}"
        )

    async def _scrape_profiles_concurrent(
        self, handles: list[str]
    ) -> list[tuple[str, dict]]:
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        async def scrape_one(handle: str) -> tuple[str, dict]:
            async with semaphore:
                loop = asyncio.get_event_loop()
                try:
                    data = await loop.run_in_executor(
                        None, lambda: self._profile_tool._run(handle)
                    )
                    return handle, data
                except Exception as e:
                    logger.error(f"Instagram profile scrape failed for @{handle}: {e}")
                    return handle, {}

        tasks = [scrape_one(h) for h in handles]
        return list(await asyncio.gather(*tasks))

    @staticmethod
    def _extract_post_caption(post: dict) -> str:
        """Extract caption text from a post dict regardless of key name."""
        for key in ("caption", "description", "text", "accessibility_caption"):
            val = post.get(key)
            if val and isinstance(val, str):
                return val.strip()
        return ""

    @staticmethod
    def _step_log(step_name: str) -> None:
        logger.info(f"--- {step_name} ---")
