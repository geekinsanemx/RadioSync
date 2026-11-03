"""radiosync json_io: portable JSON catalog export and merge import.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

import json
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import memory_rules
from .catalog import ImportReport, find_by_fingerprint, import_memories, memory_to_wire
from .chirp_client import ChirpClient
from .config import RadiosyncError
from .models import ChannelSet, Memory
from .schemas import Catalog, CatalogMember, CatalogSet
from .sets import add_member, get_or_create_set, get_set


class CatalogFileError(RadiosyncError):
    pass


def export_catalog(session: Session, set_names: list[str] | None = None) -> Catalog:
    if set_names:
        channel_sets = [get_set(session, name) for name in set_names]
        memory_ids = {m.memory_id for s in channel_sets for m in s.members}
        memories = [session.get(Memory, i) for i in sorted(memory_ids)]
    else:
        channel_sets = list(session.scalars(select(ChannelSet).order_by(ChannelSet.name)))
        memories = list(session.scalars(select(Memory).order_by(Memory.id)))
    return Catalog(
        memories=[dict(memory_to_wire(m), fingerprint=m.fingerprint) for m in memories],
        sets=[CatalogSet(name=s.name, description=s.description,
                         members=[CatalogMember(fingerprint=m.memory.fingerprint,
                                                alias=m.alias, skip=m.skip)
                                  for m in sorted(s.members, key=lambda m: m.position)])
              for s in channel_sets],
    )


def write_catalog(catalog: Catalog, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(catalog.model_dump_json(indent=2) + "\n")


def read_catalog(path: Path) -> Catalog:
    try:
        return Catalog.model_validate_json(path.read_text())
    except ValidationError as exc:
        raise CatalogFileError(f"{path.name} is not a valid radiosync catalog",
                               [f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                                for e in exc.errors()[:20]]) from exc
    except json.JSONDecodeError as exc:
        raise CatalogFileError(f"{path.name} is not valid JSON: {exc}") from exc


def import_catalog(session: Session, client: ChirpClient, catalog: Catalog,
                   set_name: str | None) -> tuple[ImportReport, list[str]]:
    """Merge @catalog; its sets merge by name, members are appended when missing."""
    payload = [m.model_dump(exclude={"fingerprint"}) for m in catalog.memories]
    normalized = client.normalize(payload) if payload else []
    remap = {}
    for original, wire in zip(catalog.memories, normalized):
        if original.fingerprint:
            remap[original.fingerprint] = wire["fingerprint"]
    wires = [{f: w[f] for f in memory_rules.WIRE_FIELDS} for w in normalized]
    report = import_memories(session, wires, set_name, "file")
    notes = []
    for catalog_set in catalog.sets:
        channel_set, created = get_or_create_set(session, catalog_set.name)
        if created:
            notes.append(f"set {catalog_set.name!r} created")
        added = 0
        for member in catalog_set.members:
            fp = remap.get(member.fingerprint, member.fingerprint)
            memory = find_by_fingerprint(session, fp)
            if memory is None:
                raise CatalogFileError(f"Set {catalog_set.name!r} references an unknown "
                                       f"memory {member.fingerprint[:12]}")
            if add_member(session, channel_set, memory, alias=member.alias,
                          skip=member.skip, missing_ok=True):
                added += 1
        notes.append(f"set {catalog_set.name!r}: {added} members added")
    return report, notes
