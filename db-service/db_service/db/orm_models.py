import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Enum, ForeignKey, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedColumn, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = MappedColumn(primary_key=True)
    name: Mapped[str] = MappedColumn(nullable=False)
    email: Mapped[str] = MappedColumn(nullable=False)
    hashed_password: Mapped[str] = MappedColumn(nullable=False)
    chatbots: Mapped[list["ChatBot"]] = relationship(back_populates="user")
    refresh_token: Mapped[str] = MappedColumn(nullable=True)


class TelegramExecutionStatusEnum(enum.Enum):
    OK = "OK"
    ERRORS = "ERRORS"
    FAILED = "FAILED"
    PENDING = "PENDING"


class VersionStatusEnum(enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class ChatBot(Base):
    __tablename__ = "chat_bots"

    id: Mapped[int] = MappedColumn(primary_key=True)
    name: Mapped[str] = MappedColumn(nullable=False)
    description: Mapped[str] = MappedColumn(nullable=False)
    user_id: Mapped[int] = MappedColumn(ForeignKey("users.id"))
    user: Mapped["User"] = relationship(back_populates="chatbots")
    executions: Mapped[list["TelegramExecution"]] = relationship(back_populates="chatbot")
    versions: Mapped[list["ChatbotVersion"]] = relationship(back_populates="chatbot")


class ChatbotVersion(Base):
    __tablename__ = "chatbot_versions"

    id: Mapped[int] = MappedColumn(primary_key=True)
    chatbot_id: Mapped[int] = MappedColumn(ForeignKey("chat_bots.id"), nullable=False)
    parent_id: Mapped[Optional[int]] = MappedColumn(ForeignKey("chatbot_versions.id"), nullable=True)
    s3_key: Mapped[str] = MappedColumn(nullable=False, unique=True)
    status: Mapped[VersionStatusEnum] = MappedColumn(
        Enum(VersionStatusEnum, native_enum=False, validate_strings=True),
        nullable=False,
        default=VersionStatusEnum.DRAFT,
    )
    author_id: Mapped[int] = MappedColumn(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = MappedColumn(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    chatbot: Mapped["ChatBot"] = relationship(back_populates="versions")
    author: Mapped["User"] = relationship()
    parent: Mapped[Optional["ChatbotVersion"]] = relationship(
        remote_side="ChatbotVersion.id",
        foreign_keys=[parent_id],
    )


class TelegramExecution(Base):
    __tablename__ = "telegram_executions"

    id: Mapped[int] = MappedColumn(primary_key=True)
    chatbot_id: Mapped[int] = MappedColumn(ForeignKey("chat_bots.id"))
    chatbot: Mapped["ChatBot"] = relationship(back_populates="executions")
    status: Mapped[TelegramExecutionStatusEnum] = MappedColumn(
        Enum(TelegramExecutionStatusEnum, native_enum=False, validate_strings=True),
        nullable=False
    )
