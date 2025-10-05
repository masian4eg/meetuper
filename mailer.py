import asyncio
import random
import logging
from typing import List
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest

logger = logging.getLogger(__name__)

class Mailer:
    """
    Mailer с простым rate limit (concurrency semaphore) и retry.
    concurrency: одновременно отправлять не более N сообщений.
    retry: при ошибках  retry с экспоненциальным бэкофом.
    """
    def __init__(self, bot: Bot, concurrency: int = 10, base_delay: float = 1.0, max_attempts: int = 5):
        self.bot = bot
        self.semaphore = asyncio.Semaphore(concurrency)
        self.base_delay = base_delay
        self.max_attempts = max_attempts

    async def _send_with_retry(self, chat_id: int, text: str, **kwargs):
        attempt = 0
        while True:
            try:
                async with self.semaphore:
                    return await self.bot.send_message(chat_id, text, **kwargs)
            except TelegramRetryAfter as e:
                # Bot is rate-limited by Telegram, wait as told
                wait = e.retry_after + 0.5
                logger.warning("Rate limited, sleeping %s seconds (TelegramRetryAfter)", wait)
                await asyncio.sleep(wait)
            except TelegramForbiddenError:
                # user blocked the bot or chat not accessible -> stop retrying
                logger.warning("Can't send message to %s: forbidden", chat_id)
                return None
            except TelegramBadRequest as e:
                # Bad request (maybe text too long, or chat not found)
                logger.warning("Bad request sending to %s: %s", chat_id, e)
                return None
            except Exception as e:
                attempt += 1
                if attempt >= self.max_attempts:
                    logger.exception("Failed to send message to %s after %s attempts", chat_id, attempt)
                    return None
                delay = self.base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.warning("Error send to %s: %s — retry %s after %.1fs", chat_id, e, attempt, delay)
                await asyncio.sleep(delay)

    async def send_batch(self, chat_ids: List[int], text: str, **kwargs):
        """
        Отправляет текст списку chat_ids параллельно с concurrency limit.
        Возвращает список ответов (None для неуспешных).
        """
        tasks = [asyncio.create_task(self._send_with_retry(cid, text, **kwargs)) for cid in chat_ids]
        results = await asyncio.gather(*tasks)
        return results
