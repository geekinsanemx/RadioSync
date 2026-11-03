"""radiosync tests: JSON catalog export and merge import.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

from radiosync import catalog, json_io, sets
from radiosync.database import Database
from radiosync.config import init_project

from .conftest import make_wire


def test_export_import_roundtrip(db, fake_client, tmp_path):
    with db.session(write=True) as session:
        catalog.import_memories(session, [make_wire("146.520", name="CALL"),
                                          make_wire("147.000", name="RPT")], "personal", "x")
        sets.update_member(session, sets.get_set(session, "personal"),
                           catalog.get_memory(session, 2), alias="R1")
    with db.session() as session:
        data = json_io.export_catalog(session)
    path = tmp_path / "out" / "cat.json"
    json_io.write_catalog(data, path)

    other = Database(init_project(tmp_path / "other"))
    other.ensure_schema()
    with other.session(write=True) as session:
        report, notes = json_io.import_catalog(session, fake_client, json_io.read_catalog(path),
                                               None)
    assert report.new == 2
    with other.session(write=True) as session:
        report, _ = json_io.import_catalog(session, fake_client, json_io.read_catalog(path), None)
        members = sets.get_set(session, "personal").members
        assert report.new == 0 and report.existing == 2
        assert [(m.memory.name, m.alias) for m in members] == [("CALL", None), ("RPT", "R1")]
