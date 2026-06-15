"""Background loop for proactive system health monitoring.

This runs as an asyncio task tied to the FastAPI lifespan, periodically
checking the health of critical systems (Scheduler, Antivirus) and
sending notifications if issues are detected.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from app.database import SessionLocal
from app.services import scheduler_health_service, av_health_service, notification_service

logger = logging.getLogger("quenza.health_monitor")

# Track the last time we sent an alert for a specific system to avoid spam.
# We'll re-alert every 12 hours if the system remains unhealthy.
_last_alert_time: dict[str, datetime] = {}
ALERT_COOLDOWN_HOURS = 12


async def start_monitor_loop():
    """Run an infinite loop checking health every 15 minutes."""
    logger.info("System health monitor loop started.")
    
    while True:
        try:
            # Check every 15 minutes
            await asyncio.sleep(15 * 60)
            
            # Offload synchronous DB checks to a thread to avoid blocking the event loop
            await asyncio.to_thread(_check_and_notify)
            
        except asyncio.CancelledError:
            logger.info("System health monitor loop stopped.")
            break
        except Exception as e:
            logger.error(f"Error in health monitor loop: {e}")
            # Sleep a bit on unexpected error before retrying
            await asyncio.sleep(60)


def _check_and_notify():
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    
    try:
        # 1. Check Scheduler Health
        sched_health = scheduler_health_service.get_health_status(db)
        _process_system_health(
            system_name="Scheduler (Cron)",
            is_healthy=sched_health.is_healthy,
            alerts=sched_health.alerts,
            warnings=[],
            now=now
        )

        # 2. Check Antivirus Health
        av_health = av_health_service.get_health_status(db)
        _process_system_health(
            system_name="Antivirus & Scanner",
            is_healthy=av_health.is_healthy,
            alerts=av_health.alerts,
            warnings=av_health.warnings,
            now=now
        )
            
    finally:
        db.close()


def _process_system_health(system_name: str, is_healthy: bool, alerts: list[str], warnings: list[str], now: datetime):
    # If healthy, clear any tracking so if it breaks again, it alerts immediately
    if is_healthy and not alerts and not warnings:
        if system_name in _last_alert_time:
            del _last_alert_time[system_name]
        return

    # If unhealthy or has warnings, check cooldown
    last_alert = _last_alert_time.get(system_name)
    if last_alert and (now - last_alert) < timedelta(hours=ALERT_COOLDOWN_HOURS):
        return  # In cooldown period, don't spam

    # Send notification
    try:
        notification_service.notify_system_health(system_name, alerts, warnings)
        _last_alert_time[system_name] = now
    except Exception as e:
        logger.error(f"Failed to send health notification for {system_name}: {e}")
