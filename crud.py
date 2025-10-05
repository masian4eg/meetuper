from datetime import datetime
from typing import Optional, Sequence
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models import User, Event, Registration, GeneratedLink
from sqlalchemy.exc import IntegrityError


async def get_user_role(session: AsyncSession, tg_id: str) -> str:
    user = await get_user_by_tg(session, tg_id)
    return user.role


async def get_user_by_tg(session: AsyncSession, tg_id: str) -> Optional[User]:
    q = await session.execute(select(User).where(User.tg_id == tg_id))
    return q.scalars().first()


async def create_user_if_not_exists(session: AsyncSession, tg_id: str, tg_username: Optional[str]=None, role: str="user"):
    user = await get_user_by_tg(session, tg_id)
    if user:
        return user
    user = User(tg_id=tg_id, tg_username=tg_username, role=role)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_event(session: AsyncSession, owner_tg_id: str, title: str, poster_text: str,
                       publish_at: datetime, reminder_at: Optional[datetime],
                       reminder_text: Optional[str], confirm_request_at: Optional[datetime],
                       confirm_text: Optional[str], category_id: Optional[int]) -> Event:
    ev = Event(
        owner_tg_id=owner_tg_id,
        title=title,
        poster_text=poster_text,
        publish_at=publish_at,
        reminder_at=reminder_at,
        reminder_text=reminder_text,
        confirm_request_at=confirm_request_at,
        confirm_text=confirm_text,
        category_id=category_id
    )
    session.add(ev)
    await session.commit()
    await session.refresh(ev)
    return ev


async def update_event(session, event_id: int, **kwargs):
    result = await session.execute(
        select(Event).where(Event.id == event_id)
    )
    ev = result.scalar_one_or_none()
    if not ev:
        return None
    for k, v in kwargs.items():
        setattr(ev, k, v)
    await session.commit()
    return ev


async def delete_event(session, event_id: int, owner_tg_id: str) -> bool:
    result = await session.execute(
        select(Event).where(Event.id == event_id, Event.owner_tg_id == owner_tg_id)
    )
    ev = result.scalar_one_or_none()
    if not ev:
        return False
    await session.delete(ev)
    await session.commit()
    return True


async def add_registration(session: AsyncSession, event_id: int, tg_id: str, role_in_event: str,
                           name: str, age: Optional[int], specialty: Optional[str],
                           company: Optional[str], talk_topic: Optional[str]) -> Registration:
    reg = Registration(
        event_id=event_id,
        tg_id=tg_id,
        role_in_event=role_in_event,
        name=name,
        age=age,
        specialty=specialty,
        company=company,
        talk_topic=talk_topic
    )
    session.add(reg)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # уже зарегистрирован — обновим существующую запись
        q = await session.execute(select(Registration).where(Registration.event_id == event_id, Registration.tg_id == tg_id))
        existing = q.scalars().first()
        if existing:
            existing.name = name
            existing.age = age
            existing.specialty = specialty
            existing.company = company
            existing.talk_topic = talk_topic
            session.add(existing)
            await session.commit()
            return existing
        raise
    await session.refresh(reg)
    return reg


async def mark_confirmed(session: AsyncSession, event_id: int, tg_id: str) -> bool:
    q = await session.execute(select(Registration).where(Registration.event_id == event_id, Registration.tg_id == tg_id))
    reg = q.scalars().first()
    if not reg:
        return False
    reg.confirmed = True
    session.add(reg)
    await session.commit()
    return True


async def get_event(session: AsyncSession, event_id: int) -> Optional[Event]:
    q = await session.execute(select(Event).where(Event.id == event_id))
    return q.scalars().first()


async def get_registrations_for_event(session: AsyncSession, event_id: int, role_filter: Optional[str]=None) -> Sequence[Registration]:
    stmt = select(Registration).where(Registration.event_id == event_id)
    if role_filter in ("listener", "speaker"):
        stmt = stmt.where(Registration.role_in_event == role_filter)
    q = await session.execute(stmt)
    return q.scalars().all()


async def save_generated_link(session: AsyncSession, event_id: int, kind: str, payload: str, expires_at: Optional[datetime]=None):
    gl = GeneratedLink(event_id=event_id, kind=kind, payload=payload, expires_at=expires_at)
    session.add(gl)
    await session.commit()
    await session.refresh(gl)
    return gl


async def get_pending_events(session: AsyncSession, now: datetime) -> Sequence[Event]:
    q = await session.execute(select(Event).where(Event.publish_at >= now))
    return q.scalars().all()


async def get_events_for_scheduler(session: AsyncSession, now: datetime):
    # load all events that have future publish/reminder/confirm dates
    q = await session.execute(
        select(Event).where(
            (Event.publish_at >= now) |
            (Event.reminder_at is not None and Event.reminder_at >= now) |
            (Event.confirm_request_at is not None and Event.confirm_request_at >= now)
        )
    )
    return q.scalars().all()


async def get_events_by_owner(session, owner_tg_id: str, upcoming: bool = True):
    stmt = select(Event).where(Event.owner_tg_id == owner_tg_id)
    stmt = stmt.where(Event.publish_at >= datetime.now()) if upcoming else stmt.where(Event.publish_at < datetime.now())
    stmt = stmt.order_by(Event.publish_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()
