"""radiosync csv_io: CHIRP CSV and image channel exchange through CHIRP's own drivers.

Changelog:
- 0.1.3 (2026-11-01): imported channels carry no power; each radio profile decides it.
- 0.1.0 (2026-11-01): initial version.
"""

from pathlib import Path

from .chirp_client import ChirpClient
from .config import RadiosyncError

READABLE_SUFFIXES = (".csv", ".img")


class ExchangeError(RadiosyncError):
    pass


def read_channels(client: ChirpClient, path: Path) -> tuple[dict, list[dict]]:
    """Memories of a CHIRP CSV or image without power, ordered by Location, rejected as a whole on errors."""
    if path.suffix.lower() not in READABLE_SUFFIXES:
        raise ExchangeError(f"Unsupported file type {path.suffix!r}; use .csv, .img or .json")
    if not path.is_file():
        raise ExchangeError(f"File not found: {path}")
    result = client.read_channels(path)
    memories = [dict(m, power_mw=None) for m in result["memories"]]
    return result["source"], memories


def write_csv(client: ChirpClient, path: Path, wires: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    return client.write_csv(path, wires)["written"]
