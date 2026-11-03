"""radiosync tests: set membership, ordering and member overrides.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

import pytest

from radiosync import catalog, sets
from radiosync.sets import SetError

from .conftest import make_wire


def _setup(session, count=4):
    report = catalog.import_memories(
        session, [make_wire(f"146.{500 + i * 20}", name=f"M{i}") for i in range(count)],
        "s", "x")
    return sets.get_set(session, "s"), [catalog.get_memory(session, i) for i in report.memory_ids]


def names(channel_set):
    return [m.memory.name for m in sorted(channel_set.members, key=lambda m: m.position)]


def test_move_insert_remove(db):
    with db.session(write=True) as session:
        channel_set, mems = _setup(session)
        sets.move_member(session, channel_set, mems[3], 1)
        assert names(channel_set) == ["M3", "M0", "M1", "M2"]
        sets.remove_member(session, channel_set, mems[0])
        assert names(channel_set) == ["M3", "M1", "M2"]
        sets.add_member(session, channel_set, mems[0], position=2)
        assert names(channel_set) == ["M3", "M0", "M1", "M2"]
        assert sorted(m.position for m in channel_set.members) == [1, 2, 3, 4]


def test_duplicate_member_and_bad_name(db):
    with db.session(write=True) as session:
        channel_set, mems = _setup(session, 1)
        with pytest.raises(SetError):
            sets.add_member(session, channel_set, mems[0])
        with pytest.raises(SetError):
            sets.create_set(session, "bad name")


def test_member_alias_and_skip(db):
    with db.session(write=True) as session:
        channel_set, mems = _setup(session, 1)
        member = sets.update_member(session, channel_set, mems[0], alias="SHORT", skip="S")
        assert (member.alias, member.skip) == ("SHORT", "S")
        member = sets.update_member(session, channel_set, mems[0], alias=None)
        assert member.alias is None and member.skip == "S"


def test_delete_set_keeps_memories(db):
    with db.session(write=True) as session:
        _setup(session, 2)
        assert sets.delete_set(session, "s") == 2
        assert len(catalog.list_memories(session)) == 2
