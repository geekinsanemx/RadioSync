"""radiosync composition: combine ordered sets into one channel list.

The "personal" set always goes first; a memory appears once, at its first occurrence.

Changelog:
- 0.1.8 (2026-11-01): optional stable sort by receive frequency.
- 0.1.7 (2026-11-01): generated comments prefix all catalog memberships.
- 0.1.0 (2026-11-01): initial version.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .catalog import memory_to_wire
from .config import RadiosyncError
from .sets import get_set

PERSONAL_SET = "personal"


class CompositionError(RadiosyncError):
    pass


@dataclass
class ComposedChannel:
    memory_id: int
    fingerprint: str
    wire: dict
    sources: list[str]


@dataclass
class Composition:
    sets: list[str]
    channels: list[ComposedChannel]
    notes: list[str] = field(default_factory=list)
    sort_by_frequency: bool = False


def order_sets(names: list[str]) -> list[str]:
    ordered = list(dict.fromkeys(n.strip() for n in names if n.strip()))
    if not ordered:
        raise CompositionError("No sets selected")
    if PERSONAL_SET in ordered:
        ordered.remove(PERSONAL_SET)
        ordered.insert(0, PERSONAL_SET)
    return ordered


def compose(session: Session, names: list[str], sort_by_frequency: bool = False) -> Composition:
    ordered = order_sets(names)
    channels: list[ComposedChannel] = []
    by_memory: dict[int, ComposedChannel] = {}
    first_member = {}
    notes = []
    for set_name in ordered:
        channel_set = get_set(session, set_name)
        for member in sorted(channel_set.members, key=lambda m: m.position):
            existing = by_memory.get(member.memory_id)
            if existing is not None:
                existing.sources.append(set_name)
                first = first_member[member.memory_id]
                if (member.alias, member.skip) != (first.alias, first.skip):
                    notes.append(f"#{member.memory_id}: alias/skip from set "
                                 f"{first.channel_set.name!r} kept over {set_name!r}")
                continue
            wire = memory_to_wire(member.memory)
            if member.alias:
                wire["name"] = member.alias
            if member.skip is not None:
                wire["skip"] = member.skip
            channel = ComposedChannel(member.memory_id, member.memory.fingerprint, wire,
                                      [set_name])
            channels.append(channel)
            by_memory[member.memory_id] = channel
            first_member[member.memory_id] = member
    for channel in channels:
        memory = first_member[channel.memory_id].memory
        memberships = [m.channel_set.name for m in memory.memberships]
        selected = [name for name in ordered if name in memberships]
        all_sets = selected + sorted(set(memberships) - set(selected))
        original = channel.wire["comment"].strip()
        prefix = f"Sets: {', '.join(all_sets)}"
        channel.wire["comment"] = prefix + (f" | {original}" if original else "")
    if sort_by_frequency:
        channels.sort(key=lambda channel: channel.wire["freq_hz"])
    return Composition(ordered, channels, notes, sort_by_frequency)
