"""radiosync tests: CLI value parsing and CSV exchange guards.

Changelog:
- 0.1.3 (2026-11-01): imports drop power.
- 0.1.0 (2026-11-01): initial version.
"""

import pytest

from radiosync.cli import edit_wire, parse_scaled
from radiosync.config import RadiosyncError
from radiosync.csv_io import ExchangeError, read_channels

from .conftest import make_wire


def test_parse_scaled_exact():
    assert parse_scaled("146.52", 1_000_000, "f") == 146_520_000
    assert parse_scaled("462.5625", 1_000_000, "f") == 462_562_500
    assert parse_scaled("88.5", 10, "t") == 885
    assert parse_scaled("0.5W", 1000, "p") == 500
    with pytest.raises(RadiosyncError):
        parse_scaled("146.5200001", 1_000_000, "f")
    with pytest.raises(RadiosyncError):
        parse_scaled("abc", 10, "t")


def test_edit_wire_options():
    wire = edit_wire(make_wire("146.520"), {"duplex": "-", "offset": "0.6", "tmode": "tsql",
                                            "ctone": "100.0", "power": "", "name": "X"}, False)
    assert (wire["duplex"], wire["offset_hz"], wire["tmode"], wire["ctone_dhz"]) == \
        ("-", 600_000, "TSQL", 1000)
    assert wire["power_mw"] is None


def test_split_requires_tx():
    with pytest.raises(Exception):
        edit_wire(make_wire("146.520"), {"duplex": "split"}, False)


def test_unsupported_suffix(tmp_path):
    path = tmp_path / "x.txt"
    path.write_text("x")
    with pytest.raises(ExchangeError):
        read_channels(None, path)


def test_import_drops_power(tmp_path):
    class Client:
        def read_channels(self, path):
            return {"source": {"type": "csv"}, "memories": [dict(make_wire(power_mw=10000), location=1)]}
    path = tmp_path / "x.csv"
    path.write_text("x")
    _, memories = read_channels(Client(), path)
    assert memories[0]["power_mw"] is None
