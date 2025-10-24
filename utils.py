import os
from datetime import datetime, UTC
from urllib.parse import quote

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import DeepLinkToken

load_dotenv()
SECRET = os.environ["SECRET_KEY"].encode()


async def verify_payload(token: str, session: AsyncSession) -> dict | None:
    q = await session.execute(select(DeepLinkToken).where(DeepLinkToken.token == token))
    obj = q.scalar_one_or_none()
    if not obj:
        return None
    if obj.expires_at and obj.expires_at < datetime.now(UTC):
        return None
    return {"kind": obj.kind, "event_id": obj.event_id}


async def make_deeplink(kind: str, event_id: int, bot_username: str, session: AsyncSession, expires_at=None) -> str:
    token = DeepLinkToken(kind=kind, event_id=event_id, expires_at=expires_at)
    session.add(token)
    await session.commit()
    await session.refresh(token)

    return f"https://t.me/{bot_username}_bot?start={quote(token.token)}"
