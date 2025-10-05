import os
from datetime import datetime, UTC
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    TIMESTAMP,
    ForeignKey,
    UniqueConstraint, DateTime, func
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

load_dotenv()

DATABASE_URL = os.getenv("DB_DSN")
engine = create_async_engine(DATABASE_URL, future=True, echo=False)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    tg_id = Column(String, unique=True, index=True, nullable=False)  # Telegram user id
    tg_username = Column(String, nullable=True)
    role = Column(String, default="user")  # user | event_admin | super_admin
    name = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.now(UTC))

    events = relationship("Event", back_populates="owner", cascade="all, delete-orphan")
    registrations = relationship("Registration", back_populates="user", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    owner_id = Column(String, ForeignKey("users.tg_id"), nullable=True)  # NULL = глобальная категория
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.now(UTC))

    owner = relationship("User")
    events = relationship("Event", back_populates="category", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    owner_tg_id = Column(String, ForeignKey("users.tg_id"), nullable=False)
    title = Column(String, nullable=False)
    poster_text = Column(Text, nullable=False)  # текст афиши
    publish_at = Column(TIMESTAMP(timezone=True), nullable=False)
    reminder_at = Column(TIMESTAMP(timezone=True), nullable=True)
    reminder_text = Column(Text, nullable=True)
    confirm_request_at = Column(TIMESTAMP(timezone=True), nullable=True)
    confirm_text = Column(Text, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.now(UTC))
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.now(UTC), onupdate=datetime.now(UTC))

    owner = relationship("User", back_populates="events")
    category = relationship("Category", back_populates="events")
    registrations = relationship("Registration", back_populates="event", cascade="all, delete-orphan")
    links = relationship("GeneratedLink", back_populates="event", cascade="all, delete-orphan")
    deeplink_tokens = relationship("DeepLinkToken", back_populates="event", cascade="all, delete-orphan")


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("event_id", "tg_id", name="uq_event_tg"),)

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"))
    tg_id = Column(String, ForeignKey("users.tg_id"), nullable=False)
    role_in_event = Column(String, nullable=False)  # listener | speaker
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=True)
    specialty = Column(String, nullable=True)
    company = Column(String, nullable=True)
    talk_topic = Column(Text, nullable=True)
    confirmed = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.now(UTC))

    event = relationship("Event", back_populates="registrations")
    user = relationship("User", back_populates="registrations")


class GeneratedLink(Base):
    __tablename__ = "generated_links"

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"))
    kind = Column(String, nullable=False)  # join | speaker | confirm
    payload = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.now(UTC))
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True)

    event = relationship("Event", back_populates="links")


class DeepLinkToken(Base):
    __tablename__ = "deeplink_tokens"

    token = Column(String(64), primary_key=True, default=lambda: uuid4().hex)
    kind = Column(String(16), nullable=False)  # join / speaker / confirm
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)

    event = relationship("Event", back_populates="deeplink_tokens")


# --- вспомогательные функции ---
async def init_db():
    """
    Создать все таблицы (для dev-режима).
    В продакшне используйте alembic для миграций.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
