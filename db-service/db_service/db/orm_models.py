import enum

from sqlalchemy import Enum, ForeignKey
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


class ChatBot(Base):
    __tablename__ = "chat_bots"

    id: Mapped[int] = MappedColumn(primary_key=True)
    name: Mapped[str] = MappedColumn(nullable=False)
    description: Mapped[str] = MappedColumn(nullable=False)
    user_id: Mapped[int] = MappedColumn(ForeignKey("users.id"))
    user: Mapped["User"] = relationship(back_populates="chatbots")
    executions: Mapped[list["TelegramExecution"]] = relationship(back_populates="chatbot")


class TelegramExecution(Base):
    __tablename__ = "telegram_executions"

    id: Mapped[int] = MappedColumn(primary_key=True)
    chatbot_id: Mapped[int] = MappedColumn(ForeignKey("chat_bots.id"))
    chatbot: Mapped["ChatBot"] = relationship(back_populates="executions")
    status: Mapped[TelegramExecutionStatusEnum] = MappedColumn(
        Enum(TelegramExecutionStatusEnum, native_enum=False, validate_strings=True),
        nullable=False
    )
