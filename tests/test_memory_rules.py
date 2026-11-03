"""radiosync tests: canonical form and fingerprint.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

from radiosync import memory_rules

from .conftest import make_wire


def test_inactive_tones_do_not_change_identity():
    a = make_wire(tmode="", rtone_dhz=885, ctone_dhz=885)
    b = make_wire(tmode="", rtone_dhz=1000, ctone_dhz=1318, dtcs=754)
    assert memory_rules.fingerprint(a) == memory_rules.fingerprint(b)


def test_active_tone_changes_identity():
    a = make_wire(tmode="TSQL", ctone_dhz=1000)
    b = make_wire(tmode="TSQL", ctone_dhz=1035)
    assert memory_rules.fingerprint(a) != memory_rules.fingerprint(b)


def test_tsql_ignores_rtone():
    a = make_wire(tmode="TSQL", rtone_dhz=885, ctone_dhz=1000)
    b = make_wire(tmode="TSQL", rtone_dhz=1318, ctone_dhz=1000)
    assert memory_rules.fingerprint(a) == memory_rules.fingerprint(b)


def test_presentation_fields_not_in_identity():
    a = make_wire(name="A", comment="x", power_mw=5000, skip="S")
    b = make_wire(name="B", comment="y", power_mw=1000, skip="")
    assert memory_rules.fingerprint(a) == memory_rules.fingerprint(b)


def test_simplex_offset_ignored_but_repeater_offset_counts():
    assert memory_rules.fingerprint(make_wire(duplex="", offset_hz=600000)) == \
        memory_rules.fingerprint(make_wire(duplex="", offset_hz=0))
    assert memory_rules.fingerprint(make_wire(duplex="+", offset_hz=600000)) != \
        memory_rules.fingerprint(make_wire(duplex="+", offset_hz=5000000))


def test_rx_only_differs_from_simplex():
    assert memory_rules.fingerprint(make_wire(duplex="off")) != \
        memory_rules.fingerprint(make_wire(duplex=""))


def test_cross_mode_fields():
    fields = memory_rules.active_tone_fields("Cross", "Tone->DTCS")
    assert fields == {"cross_mode", "rtone_dhz", "rx_dtcs", "dtcs_polarity"}
    assert memory_rules.active_tone_fields("Cross", "->Tone") == {"cross_mode", "ctone_dhz"}
