"""radiosync tests: catalog import, dedupe, manual add/edit/delete.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

import pytest

from radiosync import catalog, sets
from radiosync.catalog import CatalogError

from .conftest import make_wire


def test_import_dedupes_and_reports_conflicts(db):
    with db.session(write=True) as session:
        first = catalog.import_memories(
            session, [make_wire("146.520", name="CALL"), make_wire("146.550", name="S2")],
            "personal", "a.csv")
    assert (first.new, first.existing, first.memberships_added) == (2, 0, 2)
    with db.session(write=True) as session:
        second = catalog.import_memories(
            session, [make_wire("146.520", name="OTHER"), make_wire("146.520", name="DUP"),
                      make_wire("147.000")], "personal", "b.csv")
    assert second.new == 1
    assert second.existing == 1
    assert second.duplicates_in_file == 1
    assert second.already_members == 1
    assert any("keeping 'CALL'" in c for c in second.conflicts)
    with db.session() as session:
        names = [m.memory.name for m in sets.get_set(session, "personal").members]
    assert names == ["CALL", "S2", ""]


def test_same_frequency_different_tone_is_new(db):
    with db.session(write=True) as session:
        report = catalog.import_memories(
            session, [make_wire("462.5625", tmode=""),
                      make_wire("462.5625", tmode="Tone", rtone_dhz=670)], None, "x")
    assert report.new == 2


def test_add_duplicate_rejected_and_edit_collision(db):
    with db.session(write=True) as session:
        a = catalog.add_memory(session, make_wire("146.520", name="A"))
        b = catalog.add_memory(session, make_wire("146.550", name="B"))
        with pytest.raises(CatalogError):
            catalog.add_memory(session, make_wire("146.520", name="other name"))
        with pytest.raises(CatalogError):
            catalog.update_memory(session, b, make_wire("146.520"))
        catalog.update_memory(session, a, make_wire("146.520", name="A2", comment="c"))
        assert a.name == "A2"


def test_delete_needs_force_when_in_sets(db):
    with db.session(write=True) as session:
        report = catalog.import_memories(session, [make_wire("146.520"), make_wire("146.550")],
                                         "personal", "x")
        memory = catalog.get_memory(session, report.memory_ids[0])
        with pytest.raises(CatalogError):
            catalog.delete_memory(session, memory, force=False)
        assert catalog.delete_memory(session, memory, force=True) == ["personal"]
        positions = [m.position for m in sets.get_set(session, "personal").members]
    assert positions == [1]


def test_write_session_creates_backup(db, project):
    with db.session(write=True) as session:
        catalog.add_memory(session, make_wire())
    assert list(project.backups.glob("radiosync.db.bkp-*"))
