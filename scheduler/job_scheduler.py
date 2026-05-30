import time

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from utils.logger import get_logger

logger = get_logger(__name__)

eastern = pytz.timezone("America/New_York")


def run_comedy_run() -> None:
    from agent.comedy_agent import ComedyAgent
    logger.info("Scheduled Comedy Run triggered")
    try:
        ComedyAgent().run()
    except Exception as e:
        logger.error(f"Scheduled Comedy Run failed: {e}", exc_info=True)


def run_instagram_run() -> None:
    from agent.instagram_agent import ComedyInstagramAgent
    logger.info("Scheduled Comedy Instagram Run triggered")
    try:
        ComedyInstagramAgent().run()
    except Exception as e:
        logger.error(f"Scheduled Comedy Instagram Run failed: {e}", exc_info=True)


def run_tiktok_run() -> None:
    from agent.tiktok_agent import ComedyTikTokAgent
    logger.info("Scheduled Comedy TikTok Run triggered")
    try:
        ComedyTikTokAgent().run()
    except Exception as e:
        logger.error(f"Scheduled Comedy TikTok Run failed: {e}", exc_info=True)


def run_ticketing_run() -> None:
    from ticketing.ticketing_agent import ComedyTicketingAgent
    logger.info("Scheduled Comedy Ticketing Run triggered")
    try:
        ComedyTicketingAgent().run()
    except Exception as e:
        logger.error(f"Scheduled Comedy Ticketing Run failed: {e}", exc_info=True)


def start_scheduler() -> None:
    """Start the APScheduler and block until Ctrl+C.

    Daily schedule (all Eastern):
      11:00 AM — Web Search Run
      11:15 AM — Ticketing Run (Ticketmaster, SeatGeek, Eventbrite, StubHub)
      11:30 AM — Instagram Run
      11:45 AM — TikTok Run
    """
    scheduler = BackgroundScheduler(timezone=eastern)

    scheduler.add_job(
        run_comedy_run,
        trigger=CronTrigger(hour=11, minute=0, timezone=eastern),
        id="daily_comedy_run",
        name="Daily NYC Comedy Web Run",
        replace_existing=True,
    )
    scheduler.add_job(
        run_ticketing_run,
        trigger=CronTrigger(hour=11, minute=15, timezone=eastern),
        id="daily_comedy_ticketing_run",
        name="Daily Comedy Ticketing Run",
        replace_existing=True,
    )
    scheduler.add_job(
        run_instagram_run,
        trigger=CronTrigger(hour=11, minute=30, timezone=eastern),
        id="daily_comedy_instagram_run",
        name="Daily Comedy Instagram Run",
        replace_existing=True,
    )
    scheduler.add_job(
        run_tiktok_run,
        trigger=CronTrigger(hour=11, minute=45, timezone=eastern),
        id="daily_comedy_tiktok_run",
        name="Daily Comedy TikTok Run",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Comedy Scheduler started:")
    logger.info("  11:00 AM ET — Web Search Run")
    logger.info("  11:15 AM ET — Ticketing Run")
    logger.info("  11:30 AM ET — Instagram Run")
    logger.info("  11:45 AM ET — TikTok Run")
    logger.info("Press Ctrl+C to stop")
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down comedy scheduler…")
        scheduler.shutdown()
        logger.info("Comedy Scheduler stopped")
