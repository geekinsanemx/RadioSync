"""radiosync tests: combining sets with personal first and single occurrence.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

import pytest

from radiosync import catalog, sets
from radiosync.composition import CompositionError, compose, order_sets

from .conftest import make_wire


def test_order_sets_personal_first():
    assert order_sets(["scanner", "personal", "scanner", "x"]) == ["personal", "scanner", "x"]
    assert order_sets(["scanner"]) == ["scanner"]
    with pytest.raises(CompositionError):
        order_sets([" "])


def test_compose_dedupes_and_applies_member_overrides(db):
    with db.session(write=True) as session:
        catalog.import_memories(session, [make_wire("146.520", name="CALL"),
                                          make_wire("147.000", name="RPT")], "personal", "x")
        catalog.import_memories(session, [make_wire("162.400", name="WX1"),
                                          make_wire("146.520", name="CALL")], "scanner", "y")
        scanner = sets.get_set(session, "scanner")
        wx = catalog.find_by_fingerprint(session, catalog.memory_rules.fingerprint(
            make_wire("162.400")))
        sets.update_member(session, scanner, wx, alias="NOAA1", skip="S")
        result = compose(session, ["scanner", "personal"])
        assert result.sets == ["personal", "scanner"]
        assert [c.wire["name"] for c in result.channels] == ["CALL", "RPT", "NOAA1"]
        assert result.channels[2].wire["skip"] == "S"
        assert result.channels[0].sources == ["personal", "scanner"]


def test_compose_unknown_set(db):
    with db.session() as session:
        with pytest.raises(sets.SetError):
            compose(session, ["nope"])



def test_comments_include_all_memberships_before_original(db):
    with db.session(write=True) as session:
        wire = make_wire("146.520", name="CALL", comment="Original description")
        catalog.import_memories(session, [wire], "personal", "x")
        catalog.import_memories(session, [wire], "reference", "x")
        first = compose(session, ["personal"])
        assert first.channels[0].wire["comment"] == "Sets: personal, reference | Original description"
        second = compose(session, ["personal", "reference"])
        assert second.channels[0].wire["comment"] == first.channels[0].wire["comment"]
        assert len(second.channels) == 1
        assert catalog.get_memory(session, first.channels[0].memory_id).comment == "Original description"
        assert compose(session, ["personal"]).channels[0].wire["comment"] == first.channels[0].wire["comment"]


def test_frequency_sort_is_stable_and_keeps_distinct_programmings(db):
    with db.session(write=True) as session:
        catalog.import_memories(session, [
            make_wire("440.000", name="HIGH"),
            make_wire("146.520", name="SAME-RX-1", tmode="Tone", rtone_dhz=1000),
            make_wire("146.520", name="SAME-RX-2", tmode="Tone", rtone_dhz=1230),
            make_wire("145.000", name="LOW"),
        ], "personal", "x")
        catalog.import_memories(session, [make_wire("146.520", name="SAME-RX-1", tmode="Tone", rtone_dhz=1000)], "scanner", "x")
        default = compose(session, ["personal", "scanner"])
        ordered = compose(session, ["personal", "scanner"], sort_by_frequency=True)
        assert [c.wire["name"] for c in default.channels] == ["HIGH", "SAME-RX-1", "SAME-RX-2", "LOW"]
        assert [c.wire["name"] for c in ordered.channels] == ["LOW", "SAME-RX-1", "SAME-RX-2", "HIGH"]
        assert len(ordered.channels) == 4
