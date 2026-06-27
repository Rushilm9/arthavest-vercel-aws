"""
Scheduler — MANUAL MODE.

Per rushil.md §6.5: no cron, no interval triggers, no auto-dispatch.
The ArthaVest app runs only when the user clicks ▶ Run Discovery or ▶ Analyse All.

APScheduler is still instantiated (cheap, harmless) so future re-introduction
of scheduled jobs is a one-line change. start_scheduler() and stop_scheduler()
are kept as a stable lifespan API for app.main.
"""

try:
    from apscheduler.schedulers.background import BackgroundScheduler

    _SCHEDULER_AVAILABLE = True
except ImportError:
    BackgroundScheduler = None
    _SCHEDULER_AVAILABLE = False
from app.core.config import logger

if _SCHEDULER_AVAILABLE:
    scheduler = BackgroundScheduler()
else:
    scheduler = None


def start_scheduler():
    """Start an empty APScheduler — manual mode means no jobs are registered."""
    if scheduler is None:
        logger.info(
            "[bold yellow]APScheduler not started: package is not installed.[/bold yellow]"
        )
        return
    if not scheduler.running:
        scheduler.start()
        logger.info(
            "[bold green]APScheduler started — manual mode, no jobs registered.[/bold green]"
        )


def stop_scheduler():
    """Stop the scheduler. Also drains the discovery job pool used by /discover/jobs."""
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[bold yellow]APScheduler stopped.[/bold yellow]")
    try:
        from app.services.discovery_cache import shutdown as _ds

        _ds()
    except Exception:
        pass
