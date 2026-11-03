"""radiosync sets: ordered channel sets that reference catalog memories.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import RadiosyncError
from .models import ChannelSet, Memory, SetMember
from .schemas import SET_NAME_PATTERN

UNSET = object()


class SetError(RadiosyncError):
    pass


def validate_name(name: str) -> str:
    if not re.match(SET_NAME_PATTERN, name):
        raise SetError(f"Invalid set name {name!r}",
                       ["use letters, digits, '_', '-' or '.', starting with a letter or digit"])
    return name


def get_set(session: Session, name: str) -> ChannelSet:
    channel_set = session.scalar(select(ChannelSet).where(ChannelSet.name == name))
    if channel_set is None:
        raise SetError(f"Set {name!r} does not exist")
    return channel_set


def create_set(session: Session, name: str, description: str = "") -> ChannelSet:
    validate_name(name)
    if session.scalar(select(ChannelSet).where(ChannelSet.name == name)) is not None:
        raise SetError(f"Set {name!r} already exists")
    channel_set = ChannelSet(name=name, description=description)
    session.add(channel_set)
    session.flush()
    return channel_set


def get_or_create_set(session: Session, name: str) -> tuple[ChannelSet, bool]:
    channel_set = session.scalar(select(ChannelSet).where(ChannelSet.name == name))
    if channel_set is not None:
        return channel_set, False
    return create_set(session, name), True


def delete_set(session: Session, name: str) -> int:
    channel_set = get_set(session, name)
    count = len(channel_set.members)
    session.delete(channel_set)
    session.flush()
    return count


def list_sets(session: Session) -> list[tuple[ChannelSet, int]]:
    counts = (select(ChannelSet, func.count(SetMember.id))
              .outerjoin(SetMember).group_by(ChannelSet.id).order_by(ChannelSet.name))
    return [(row[0], row[1]) for row in session.execute(counts)]


def renumber(channel_set: ChannelSet) -> None:
    for position, member in enumerate(sorted(channel_set.members, key=lambda m: m.position),
                                      start=1):
        member.position = position


def find_member(channel_set: ChannelSet, memory: Memory) -> SetMember | None:
    for member in channel_set.members:
        if member.memory_id == memory.id:
            return member
    return None


def add_member(session: Session, channel_set: ChannelSet, memory: Memory,
               position: int | None = None, alias: str | None = None,
               skip: str | None = None, missing_ok: bool = False) -> bool:
    """Append or insert @memory; False when already a member and @missing_ok."""
    if find_member(channel_set, memory) is not None:
        if missing_ok:
            return False
        raise SetError(f"Memory #{memory.id} is already in set {channel_set.name!r}")
    count = len(channel_set.members)
    if position is None or position > count:
        position = count + 1
    if position < 1:
        raise SetError("Position starts at 1")
    for member in channel_set.members:
        if member.position >= position:
            member.position += 1
    channel_set.members.append(SetMember(memory=memory, position=position, alias=alias,
                                         skip=skip))
    session.flush()
    renumber(channel_set)
    return True


def remove_member(session: Session, channel_set: ChannelSet, memory: Memory) -> None:
    member = find_member(channel_set, memory)
    if member is None:
        raise SetError(f"Memory #{memory.id} is not in set {channel_set.name!r}")
    channel_set.members.remove(member)
    session.flush()
    renumber(channel_set)


def move_member(session: Session, channel_set: ChannelSet, memory: Memory,
                position: int) -> None:
    member = find_member(channel_set, memory)
    if member is None:
        raise SetError(f"Memory #{memory.id} is not in set {channel_set.name!r}")
    ordered = [m for m in sorted(channel_set.members, key=lambda m: m.position)
               if m is not member]
    position = max(1, min(position, len(ordered) + 1))
    ordered.insert(position - 1, member)
    for index, item in enumerate(ordered, start=1):
        item.position = index
    session.flush()


def update_member(session: Session, channel_set: ChannelSet, memory: Memory,
                  alias=UNSET, skip=UNSET) -> SetMember:
    member = find_member(channel_set, memory)
    if member is None:
        raise SetError(f"Memory #{memory.id} is not in set {channel_set.name!r}")
    if alias is not UNSET:
        member.alias = alias or None
    if skip is not UNSET:
        member.skip = skip
    session.flush()
    return member
