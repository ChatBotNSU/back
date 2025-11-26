import enum

from sqlalchemy import JSON, ForeignKey
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

class ChatBot(Base):
    __tablename__ = "chat_bots"

    id: Mapped[int] = MappedColumn(primary_key=True)
    name: Mapped[str] = MappedColumn(nullable=False)
    description: Mapped[str] = MappedColumn(nullable=False)
    user_id: Mapped[int] = MappedColumn(ForeignKey("users.id"))
    user: Mapped["User"] = relationship(back_populates="chatbots")
    key: Mapped[str] = MappedColumn(nullable=False)