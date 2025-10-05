import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from aiogram import Bot
from dotenv import load_dotenv

from models import AsyncSessionLocal
from crud import get_event, get_events_for_scheduler, get_registrations_for_event, save_generated_link
from utils import make_deeplink
from mailer import Mailer

load_dotenv()
logger = logging.getLogger(__name__)


async def send_poster_job(event_id: int, bot: Bot):
    async with AsyncSessionLocal() as session:
        ev = await get_event(session, event_id)
        if not ev:
            logger.warning("Event %s not found for publish job", event_id)
            return

        bot_username = os.getenv("BOT_USERNAME", "")
        join_link = make_deeplink("join", ev.id, bot_username)
        speaker_link = make_deeplink("speaker", ev.id, bot_username)

        text = f"{ev.poster_text}\n\nРегистрация слушателей: {join_link}\nРегистрация докладчиков: {speaker_link}"

        mailer = Mailer(bot, concurrency=10)

        # Отправляем владельцу события
        owner_chat = ev.owner.tg_id if getattr(ev, "owner", None) else None
        if owner_chat:
            await mailer.send_batch([owner_chat], text)
            logger.info("Sent preview to owner of event %s", event_id)

        # Отправляем в канал/группу BROADCAST_CHAT_ID
        broadcast = os.getenv("BROADCAST_CHAT_ID")
        if broadcast:
            try:
                broadcast_id = int(broadcast)
                await mailer.send_batch([broadcast_id], text, disable_notification=False)
                logger.info("Published event %s to broadcast %s", event_id, broadcast_id)
            except ValueError:
                logger.warning("BROADCAST_CHAT_ID not an int: %s", broadcast)


async def send_reminder_job(event_id: int, bot: Bot):
    async with AsyncSessionLocal() as session:
        ev = await get_event(session, event_id)
        if not ev or not ev.reminder_text:
            return

        regs = await get_registrations_for_event(session, event_id)
        if not regs:
            return

        mailer = Mailer(bot, concurrency=10)
        chat_ids = [r.tg_id for r in regs]
        await mailer.send_batch(chat_ids, ev.reminder_text)
        logger.info("Sent reminder for event %s to %s users", event_id, len(chat_ids))


async def send_confirm_request_job(event_id: int, bot: Bot):
    async with AsyncSessionLocal() as session:
        ev = await get_event(session, event_id)
        if not ev or not ev.confirm_text:
            return

        regs = await get_registrations_for_event(session, event_id)
        if not regs:
            return

        bot_username = os.getenv("BOT_USERNAME", "")
        confirm_link = await make_deeplink("confirm", ev.id, bot_username, session)
        await save_generated_link(session, ev.id, "confirm", confirm_link)

        text = f"{ev.confirm_text}\nПодтвердить участие: {confirm_link}"

        mailer = Mailer(bot, concurrency=10)
        chat_ids = [r.tg_id for r in regs]
        await mailer.send_batch(chat_ids, text)
        logger.info("Sent confirm requests for event %s", event_id)


async def schedule_event_jobs_for_event(ev, bot: Bot, scheduler: AsyncIOScheduler):
    """Добавляем job'ы для события, если даты в будущем"""
    now = datetime.now(timezone.utc)

    if ev.publish_at and ev.publish_at > now:
        scheduler.add_job(
            send_poster_job,
            trigger=DateTrigger(run_date=ev.publish_at),
            args=(ev.id, bot),
            id=f"event_{ev.id}_publish",
            replace_existing=True
        )
        logger.info("Scheduled publish for event %s at %s", ev.id, ev.publish_at)

    if ev.reminder_at and ev.reminder_at > now:
        scheduler.add_job(
            send_reminder_job,
            trigger=DateTrigger(run_date=ev.reminder_at),
            args=(ev.id, bot),
            id=f"event_{ev.id}_reminder",
            replace_existing=True
        )
        logger.info("Scheduled reminder for event %s at %s", ev.id, ev.reminder_at)

    if ev.confirm_request_at and ev.confirm_request_at > now:
        scheduler.add_job(
            send_confirm_request_job,
            trigger=DateTrigger(run_date=ev.confirm_request_at),
            args=(ev.id, bot),
            id=f"event_{ev.id}_confirm",
            replace_existing=True
        )
        logger.info("Scheduled confirm request for event %s at %s", ev.id, ev.confirm_request_at)


async def init_scheduler(bot: Bot, scheduler: AsyncIOScheduler):
    """Инициализация: считываем все события с будущими датами и планируем их"""
    logger.info("Initializing scheduler...")
    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        events = await get_events_for_scheduler(session, now)
        for ev in events:
            await schedule_event_jobs_for_event(ev, bot, scheduler)
    logger.info("Scheduler init done.")


def remove_event_jobs(event_id: int, scheduler: AsyncIOScheduler):
    """Удаляем джобы события"""
    for kind in ("publish", "reminder", "confirm"):
        job_id = f"event_{event_id}_{kind}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info("Removed job %s", job_id)
