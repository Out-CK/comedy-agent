from __future__ import annotations

from typing import List, Optional

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from utils.logger import get_logger

logger = get_logger(__name__)

MODEL = "claude-sonnet-4-6"
BATCH_SIZE = 3

SYSTEM_PROMPT = """You are a comedy event data extraction specialist. For each web page provided,
extract all individual NYC comedy show events mentioned.

Rules:
- Create a SEPARATE entry for each distinct show date found on a page.
- Set event_type = "comedy" always. Skip concerts, sports, theater plays, films, and conferences.
- INCLUDE: stand-up comedy, improv shows, sketch comedy, open mic nights, comedy festivals,
  roasts, storytelling nights, late-night comedy, alternative comedy.
- event_title format: "[Comedian/Show Name] at [Venue]" for headliners,
  "[Show Name] at [Venue]" for ensemble/improv/open-mic shows.
- The artist field should be the headlining comedian's name, or the show/troupe name for
  ensemble shows (e.g., "UCB Harold Night", "Magnet Mixer").
- date format: "MM-DD-YYYY" (e.g., "06-15-2026")
- start_time / end_time format: "00:00am" or "00:00pm" (e.g., "08:00pm")
- If artist/show name, venue, OR date cannot be confidently extracted, SKIP that entry.
- If a page has ticket purchase links, populate tickets_source_1 with the ticket URL.
  Otherwise use no_tickets_source_1 with the page URL as the source.
- DO NOT set event_entry_id or entry_batch_id — leave them as empty strings "".
- For the `media_url` field: look for image markdown tags in the page content (format: ![alt](url)).
  Extract the URL of the most relevant image — prefer event posters, comedian headshots, show artwork,
  or venue hero images. Skip navigation icons, logos under 100px, social media share buttons,
  tracking pixels, and ad banners. If no suitable image is found, leave media_url as null.
- Return a JSON object with key "entries" containing an array of EventEntry objects.
"""


class EventEntry(BaseModel):
    event_entry_id: str = ""
    entry_batch_id: str = ""
    event_title: str
    description: str
    artist: str
    venue: str
    event_type: str = "comedy"
    multi_day_event: bool
    date: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    tickets_source_1: Optional[str] = None
    tickets_webpage_contents_1: Optional[str] = None
    tickets_source_2: Optional[str] = None
    tickets_webpage_contents_2: Optional[str] = None
    tickets_source_3: Optional[str] = None
    tickets_webpage_contents_3: Optional[str] = None
    tickets_source_4: Optional[str] = None
    tickets_webpage_contents_4: Optional[str] = None
    no_tickets_source_1: Optional[str] = None
    no_tickets_webpage_contents_1: Optional[str] = None
    no_tickets_source_2: Optional[str] = None
    no_tickets_webpage_contents_2: Optional[str] = None
    no_tickets_source_3: Optional[str] = None
    no_tickets_webpage_contents_3: Optional[str] = None
    no_tickets_source_4: Optional[str] = None
    no_tickets_webpage_contents_4: Optional[str] = None
    media_url: Optional[str] = None
    webpage_contents: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class EntryList(BaseModel):
    entries: List[EventEntry]


class WebBatchParser:
    def __init__(self):
        self._llm = ChatAnthropic(model=MODEL).with_structured_output(EntryList)

    def parse(self, web_batch: list[dict]) -> list[EventEntry]:
        logger.info(f"WebBatchParser processing {len(web_batch)} pages in batches of {BATCH_SIZE}…")
        all_entries: list[EventEntry] = []

        for batch_start in range(0, len(web_batch), BATCH_SIZE):
            batch = web_batch[batch_start: batch_start + BATCH_SIZE]
            try:
                entries = self._parse_batch(batch)
                logger.info(
                    f"Batch {batch_start}–{batch_start + len(batch)}: parsed {len(entries)} entries"
                )
                all_entries.extend(entries)
            except Exception as e:
                logger.error(
                    f"WebBatchParser batch {batch_start}–{batch_start + len(batch)} failed: {e}"
                )

        logger.info(f"WebBatchParser total entries parsed: {len(all_entries)}")
        return all_entries

    def _parse_batch(self, batch: list[dict]) -> list[EventEntry]:
        pages_text = ""
        for record in batch:
            content_snippet = (record.get("content") or "")[:8000]
            pages_text += (
                f"\n\n---\n"
                f"PAGE URL: {record.get('url', '')}\n"
                f"QUERY USED: {record.get('query_used', '')}\n"
                f"CONTENT:\n{content_snippet}"
            )

        result: EntryList = self._llm.invoke(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract comedy show entries from these pages:{pages_text}"},
            ]
        )
        entries = result.entries or []
        for entry in entries:
            entry.event_type = "comedy"  # enforce
            if not entry.webpage_contents:
                for record in batch:
                    if record.get("url"):
                        entry.webpage_contents = (record.get("content") or "")[:10000]
                        break
        return entries
