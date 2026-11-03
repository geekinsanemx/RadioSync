"""radiosync models: SQLAlchemy ORM for memories, sets and set membership.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    freq_hz: Mapped[int] = mapped_column(BigInteger)
    duplex: Mapped[str] = mapped_column(String(8))
    offset_hz: Mapped[int] = mapped_column(BigInteger)
    mode: Mapped[str] = mapped_column(String(16))
    tmode: Mapped[str] = mapped_column(String(16))
    rtone_dhz: Mapped[int] = mapped_column(Integer)
    ctone_dhz: Mapped[int] = mapped_column(Integer)
    dtcs: Mapped[int] = mapped_column(Integer)
    rx_dtcs: Mapped[int] = mapped_column(Integer)
    dtcs_polarity: Mapped[str] = mapped_column(String(2))
    cross_mode: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64))
    comment: Mapped[str] = mapped_column(Text)
    skip: Mapped[str] = mapped_column(String(1))
    power_mw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tuning_step_hz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    memberships: Mapped[list["SetMember"]] = relationship(back_populates="memory")


class ChannelSet(Base):
    __tablename__ = "channel_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    members: Mapped[list["SetMember"]] = relationship(
        back_populates="channel_set", order_by="SetMember.position",
        cascade="all, delete-orphan")


class SetMember(Base):
    __tablename__ = "set_members"
    __table_args__ = (UniqueConstraint("set_id", "memory_id", name="uq_set_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    set_id: Mapped[int] = mapped_column(ForeignKey("channel_sets.id", ondelete="CASCADE"))
    memory_id: Mapped[int] = mapped_column(ForeignKey("memories.id", ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(Integer)
    alias: Mapped[str | None] = mapped_column(String(64), nullable=True)
    skip: Mapped[str | None] = mapped_column(String(1), nullable=True)

    channel_set: Mapped[ChannelSet] = relationship(back_populates="members")
    memory: Mapped[Memory] = relationship(back_populates="memberships")
