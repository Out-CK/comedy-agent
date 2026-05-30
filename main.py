"""
CLI entrypoint for the Comedy Agent.

Usage:
    python main.py --run-now         # Web search run immediately
    python main.py --schedule        # Start the daily scheduler (blocks until Ctrl+C)
    python main.py --instagram       # Instagram run immediately
    python main.py --tiktok          # TikTok run immediately
    python main.py --ticketing-run   # Ticketmaster/SeatGeek/Eventbrite/StubHub run immediately
"""
import argparse
import os
import sys

from dotenv import load_dotenv

from utils.logger import get_logger, setup_root_logger

REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "NIMBLE_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
]


def validate_env() -> None:
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        print(
            f"ERROR: Missing required environment variable(s): {', '.join(missing)}\n"
            "Copy .env.example to .env and fill in all values.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    load_dotenv()
    setup_root_logger()
    validate_env()

    logger = get_logger(__name__)

    parser = argparse.ArgumentParser(description="Comedy Agent CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-now", action="store_true", help="Trigger a Comedy Web Run immediately")
    group.add_argument("--schedule", action="store_true", help="Start the daily scheduler")
    group.add_argument("--instagram", action="store_true", help="Trigger an Instagram Run immediately")
    group.add_argument("--tiktok", action="store_true", help="Trigger a TikTok Run immediately")
    group.add_argument("--ticketing-run", action="store_true", help="Query ticketing platforms immediately")
    group.add_argument("--enrich-venues", action="store_true", help="Find addresses for unmapped venues")
    args = parser.parse_args()

    from db.supabase_client import get_supabase_client
    get_supabase_client()

    if args.run_now:
        logger.info("Mode: --run-now | Triggering immediate Comedy Web Run")
        from agent.comedy_agent import ComedyAgent
        ComedyAgent().run()

    elif args.schedule:
        logger.info("Mode: --schedule | Starting daily comedy scheduler")
        from scheduler.job_scheduler import start_scheduler
        start_scheduler()

    elif args.instagram:
        logger.info("Mode: --instagram | Triggering immediate Comedy Instagram Run")
        from agent.instagram_agent import ComedyInstagramAgent
        ComedyInstagramAgent().run()

    elif args.tiktok:
        logger.info("Mode: --tiktok | Triggering immediate Comedy TikTok Run")
        from agent.tiktok_agent import ComedyTikTokAgent
        ComedyTikTokAgent().run()

    elif args.ticketing_run:
        logger.info("Mode: --ticketing-run | Querying ticketing platforms")
        from ticketing.ticketing_agent import ComedyTicketingAgent
        ComedyTicketingAgent().run()

    elif args.enrich_venues:
        logger.info("Mode: --enrich-venues | Finding addresses for unmapped venues")
        from agent.venue_enricher import VenueEnricher
        VenueEnricher(event_type="comedy").run()


if __name__ == "__main__":
    main()
