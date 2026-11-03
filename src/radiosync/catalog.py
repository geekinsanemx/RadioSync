"""radiosync catalog: memory storage, deduplicating import and manual edits.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import memory_rules
from .config import RadiosyncError
from .models import Memory, SetMember
from .sets import add_member, get_or_create_set, get_set, renumber

PRESENTATION_FIELDS = ("name", "comment", "skip", "power_mw", "tuning_step_hz")


class CatalogError(RadiosyncError):
    pass


@dataclass
class ImportReport:
    read: int = 0
    new: int = 0
    existing: int = 0
    duplicates_in_file: int = 0
    memberships_added: int = 0
    already_members: int = 0
    set_created: bool = False
    conflicts: list[str] = field(default_factory=list)
    memory_ids: list[int] = field(default_factory=list)


def memory_to_wire(memory: Memory) -> dict:
    return {f: getattr(memory, f) for f in memory_rules.WIRE_FIELDS}


def _apply_wire(memory: Memory, wire: dict) -> None:
    canon = memory_rules.canonical(wire)
    for name in memory_rules.WIRE_FIELDS:
        setattr(memory, name, canon[name])
    memory.fingerprint = memory_rules.fingerprint(canon)


def find_by_fingerprint(session: Session, fingerprint: str) -> Memory | None:
    return session.scalar(select(Memory).where(Memory.fingerprint == fingerprint))


def get_memory(session: Session, memory_id: int) -> Memory:
    memory = session.get(Memory, memory_id)
    if memory is None:
        raise CatalogError(f"Memory #{memory_id} does not exist")
    return memory


def _conflicts(existing: Memory, wire: dict, label: str) -> list[str]:
    canon = memory_rules.canonical(wire)
    found = []
    for name in PRESENTATION_FIELDS:
        incoming = canon[name]
        current = getattr(existing, name)
        if incoming != current and incoming not in ("", None):
            found.append(f"#{existing.id} {name}: keeping {current!r}, {label} has {incoming!r}")
    return found


def import_memories(session: Session, wires: list[dict], set_name: str | None,
                    label: str) -> ImportReport:
    """Add new programmings, reuse identical ones, and append them to @set_name."""
    report = ImportReport(read=len(wires))
    channel_set = None
    if set_name:
        channel_set, report.set_created = get_or_create_set(session, set_name)
    seen: set[str] = set()
    for wire in wires:
        fp = memory_rules.fingerprint(wire)
        if fp in seen:
            report.duplicates_in_file += 1
            continue
        seen.add(fp)
        memory = find_by_fingerprint(session, fp)
        if memory is None:
            memory = Memory()
            _apply_wire(memory, wire)
            session.add(memory)
            session.flush()
            report.new += 1
        else:
            report.existing += 1
            report.conflicts.extend(_conflicts(memory, wire, label))
        report.memory_ids.append(memory.id)
        if channel_set is not None:
            if add_member(session, channel_set, memory, missing_ok=True):
                report.memberships_added += 1
            else:
                report.already_members += 1
    return report


def add_memory(session: Session, wire: dict) -> Memory:
    fp = memory_rules.fingerprint(wire)
    existing = find_by_fingerprint(session, fp)
    if existing is not None:
        raise CatalogError(f"The same programming already exists as #{existing.id} "
                           f"({existing.name!r})")
    memory = Memory()
    _apply_wire(memory, wire)
    session.add(memory)
    session.flush()
    return memory


def update_memory(session: Session, memory: Memory, wire: dict) -> Memory:
    fp = memory_rules.fingerprint(wire)
    existing = find_by_fingerprint(session, fp)
    if existing is not None and existing.id != memory.id:
        raise CatalogError(f"The edited programming already exists as #{existing.id} "
                           f"({existing.name!r})")
    _apply_wire(memory, wire)
    session.flush()
    return memory


def delete_memory(session: Session, memory: Memory, force: bool) -> list[str]:
    set_names = [m.channel_set.name for m in memory.memberships]
    if set_names and not force:
        raise CatalogError(f"Memory #{memory.id} is used by sets: {', '.join(set_names)}",
                           ["remove it from those sets or use --force"])
    for membership in list(memory.memberships):
        channel_set = membership.channel_set
        channel_set.members.remove(membership)
        session.flush()
        renumber(channel_set)
    session.delete(memory)
    session.flush()
    return set_names


def list_memories(session: Session, set_name: str | None = None,
                  search: str | None = None) -> list[tuple[Memory, SetMember | None]]:
    if set_name:
        channel_set = get_set(session, set_name)
        rows = [(m.memory, m) for m in sorted(channel_set.members, key=lambda m: m.position)]
        if search:
            needle = search.lower()
            rows = [(mem, m) for mem, m in rows
                    if needle in mem.name.lower() or needle in mem.comment.lower()
                    or needle in (m.alias or "").lower()]
        return rows
    query = select(Memory).order_by(Memory.freq_hz, Memory.id)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Memory.name.ilike(pattern), Memory.comment.ilike(pattern)))
    return [(memory, None) for memory in session.scalars(query)]
