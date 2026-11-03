"""radiosync tests: name fitting.

Changelog:
- 0.1.11 (2026-11-02): English stopword cases alongside the Spanish ones.
- 0.1.10 (2026-11-02): neutral place-name examples.
- 0.1.9 (2026-11-01): generic example names.
- 0.1.4 (2026-11-01): initial version.
"""

import pytest

from radiosync.names import clean_name, fit_name, fit_names


@pytest.mark.parametrize("name,limit,expected", [
    ("REP-ABC-123", 6, "ABC123"),
    ("REP-ABC-456", 6, "ABC456"),
    ("REP-ABC-123", 12, "REP-ABC-123"),
    ("NOAA-WX1", 6, "NWX1"),
    ("NOAA-WX1", 7, "NOAAWX1"),
    ("Cerro Alto", 6, "CrrAlt"),
    ("Pueblo Sur", 6, "PblSr"),
    ("Loma Roja", 6, "LomaRj"),
    ("Esplanada y", 6, "Esplnd"),
    ("Hill of Peace", 6, "HillPc"),
    ("The Old Mill", 6, "OldMll"),
    ("Bread and Butter", 6, "BrdBtt"),
    ("Hill of Peace 2", 6, "Peace2"),
    ("1.25M-223.50", 6, "223.50"),
    ("2M-146.520", 6, "146.52"),
    ("ABC", 6, "ABC"),
])
def test_fit_name(name, limit, expected):
    assert fit_name(name, limit) == expected
    assert len(fit_name(name, limit)) <= limit


@pytest.mark.parametrize("first,second", [
    ("Valle de Paz", "Valle de Pazo"),
    ("Hill of Peace", "Hill of Peach"),
])
def test_fit_names_resolves_collisions(first, second):
    names = [first, second, "RPT-C", "RPT-C"]
    fitted = fit_names(names, 5)
    assert all(len(n) <= 5 for n in fitted)
    assert fitted[0] != fitted[1]
    assert fitted[2] == fitted[3] == "RPT-C"


def test_fit_names_keeps_existing_short_names():
    fitted = fit_names(["ABC123", "REP-ABC-123"], 6)
    assert fitted[0] == "ABC123"
    assert fitted[1] != "ABC123" and len(fitted[1]) <= 6


def test_clean_name_invalid_chars():
    charset = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -"
    assert clean_name("REP.UNO", charset) == "REP UNO"
    assert fit_names(["REP.UNO", "VHF C.AB"], 6, charset) == ["REPUNO", "VHFCAB"]
    assert clean_name("Cerro.Alto", None) == "Cerro.Alto"
