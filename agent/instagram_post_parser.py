"""
InstagramPostParser — parses scraped Instagram profile content into comedy EventEntry objects.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from agent.web_batch_parser import EventEntry
from utils.logger import get_logger

logger = get_logger(__name__)

MODEL = "claude-sonnet-4-6"
BATCH_SIZE = 4

SYSTEM_PROMPT_TEMPLATE = """You are a comedy event data extraction specialist analyzing scraped Instagram profiles.
Your job is to find upcoming NYC comedy shows announced in the posts and captions.

Today's date is {today}. Only extract shows with dates AFTER today.

Rules:
- Extract only comedy shows taking place in New York City (Manhattan, Brooklyn, Queens, Bronx, Staten Island).
- INCLUDE: stand-up comedy, improv shows, sketch comedy, open mic nights, comedy festivals, roasts.
- Set event_type = "comedy". Skip concerts, sports, theater plays, art exhibitions, film screenings.
- event_title format: "[Comedian/Show Name] at [Venue]"
- The artist field = headlining comedian name, or show/troupe name for ensemble shows.
- date format: "MM-DD-YYYY" (e.g. "06-15-2026")
- start_time / end_time format: "00:00am" or "00:00pm" (e.g. "08:00pm")
- If comedian/show name, venue, OR date cannot be confidently determined, SKIP that entry entirely.
- For ticket links found in post captions or bios, populate tickets_source_1 with the URL.
  Otherwise use no_tickets_source_1 with the Instagram profile URL as the source.
- DO NOT set event_entry_id or entry_batch_id — leave them as empty strings "".
- Return JSON with key "entries" containing an array of EventEntry objects.

Instagram-specific guidance:
- Dates may appear as "June 15", "6/15", "06.15" — convert to MM-DD-YYYY using {year} as the year
  unless the post clearly states a different year.
- If a post mentions "TONIGHT" or "THIS FRIDAY", use today's date or the next matching weekday.
- Ticket links (ticketmaster.com, eventbrite.com, stubhub.com, dice.fm, linktr.ee) → tickets_source_1.
"""


class EntryList(BaseModel):
    entries: List[EventEntry]


class InstagramPostParser:
    def __init__(self):
        today = date.today()
        self._system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            today=today.strftime("%m-%d-%Y"),
            year=today.year,
        )
        self._llm = ChatAnthropic(model=MODEL).with_structured_output(EntryList)

    def parse(self, post_pages: list[dict]) -> list[EventEntry]:
        logger.info(
            f"InstagramPostParser: processing {len(post_pages)} profiles "
            f"in batches of {BATCH_SIZE}"
        )
        all_entries: list[EventEntry] = []

        for batch_start in range(0, len(post_pages), BATCH_SIZE):
            batch = post_pages[batch_start: batch_start + BATCH_SIZE]
            try:
                entries = self._parse_batch(batch)
                logger.info(
                    f"Batch {batch_start}–{batch_start + len(batch)}: "
                    f"parsed {len(entries)} entries"
                )
                all_entries.extend(entries)
            except Exception as e:
                logger.error(
                    f"InstagramPostParser batch "
                    f"{batch_start}–{batch_start + len(batch)} failed: {e}"
                )

        logger.info(f"InstagramPostParser total entries: {len(all_entries)}")
        return all_entries

    def _parse_batch(self, batch: list[dict]) -> list[EventEntry]:
        pages_text = ""
        for record in batch:
            content_snippet = (record.get("content") or "")[:6000]
            pages_text += (
                f"\n\n---\n"
                f"INSTAGRAM PROFILE URL: {record.get('url', '')}\n"
                f"SCRAPED CONTENT:\n{content_snippet}"
            )

        result: EntryList = self._llm.invoke([
            {"role": "system", "content": self._system_prompt},
            {
                "role": "user",
                "content": (
                    "Extract upcoming NYC comedy show entries from these Instagram profiles:"
                    + pages_text
                ),
            },
        ])
        entries = result.entries or []

        for entry in entries:
            entry.event_type = "comedy"
            if not entry.no_tickets_source_1 and not entry.tickets_source_1:
                for record in batch:
                    if record.get("url"):
                        entry.no_tickets_source_1 = record["url"]
                        entry.no_tickets_webpage_contents_1 = (
                            (record.get("content") or "")[:10000]
                        )
                        break

        return entries
