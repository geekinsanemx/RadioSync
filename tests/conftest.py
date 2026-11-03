"""radiosync tests: shared fixtures.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

import pytest

from radiosync import memory_rules
from radiosync.config import init_project
from radiosync.database import Database
from radiosync.schemas import MemoryInput


def make_wire(freq_mhz: str = "146.520", **fields) -> dict:
    hz = int(round(float(freq_mhz) * 1_000_000))
    return MemoryInput(freq_hz=hz, **fields).model_dump()


class FakeClient:
    """Stands in for ChirpClient where CHIRP itself is not under test."""

    def normalize(self, memories):
        out = []
        for wire in memories:
            canon = memory_rules.canonical(wire)
            canon["fingerprint"] = memory_rules.fingerprint(canon)
            out.append(canon)
        return out


@pytest.fixture
def project(tmp_path):
    return init_project(tmp_path)


@pytest.fixture
def db(project):
    database = Database(project)
    database.ensure_schema()
    return database


@pytest.fixture
def fake_client():
    return FakeClient()
