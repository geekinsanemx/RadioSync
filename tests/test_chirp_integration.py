"""radiosync tests: real CHIRP drivers: register, build, validate, tamper, settings.

Runs only when RADIOSYNC_TEST_TEMPLATE points to a radio image downloaded with CHIRP.
The image is copied into a temporary project and never modified.

Changelog:
- 0.1.2 (2026-11-01): forced and default power levels.
- 0.1.0 (2026-11-01): initial version.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from radiosync import build, catalog, validation
from radiosync.chirp_client import ChirpClient
from radiosync.config import ConfigError, chirp_python
from radiosync.radios import register, save_profile, load_profile

from .conftest import make_wire

TEMPLATE = os.environ.get("RADIOSYNC_TEST_TEMPLATE")
pytestmark = [pytest.mark.chirp,
              pytest.mark.skipif(not TEMPLATE, reason="RADIOSYNC_TEST_TEMPLATE not set")]


@pytest.fixture
def client(project):
    try:
        return ChirpClient(chirp_python(project))
    except ConfigError as exc:
        pytest.skip(str(exc))


@pytest.fixture
def registered(project, client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "source.img"
    shutil.copyfile(TEMPLATE, source)
    profile, info, _ = register(project, client, source)
    return profile, info


def _fill(db, count):
    wires = [make_wire(f"{146.400 + i * 0.020:.3f}", name=f"T{i}") for i in range(count)]
    with db.session(write=True) as session:
        catalog.import_memories(session, wires, "personal", "test")


def test_build_validate_and_tamper(project, db, client, registered):
    profile, _ = registered
    _fill(db, 5)
    with db.session() as session:
        targets = build.plan(project, session, [profile.id], None, None)
    results = build.run(project, client, targets, dry_run=False)
    assert results[0].ok, results[0].details
    manifest = results[0].manifest
    data = json.loads(manifest.read_text())
    assert len(data["channels"]) == 5
    assert validation.validate(client, manifest).ok
    assert manifest.parent == Path.cwd()
    assert validation.latest_manifests(project, [profile.id]) == [manifest]

    image = results[0].image
    original = image.read_bytes()
    image.write_bytes(original[:100] + bytes([original[100] ^ 0xFF]) + original[101:])
    assert not validation.validate(client, manifest).ok
    image.write_bytes(original)
    assert validation.validate(client, manifest).ok


def test_unknown_setting_rejected(project, db, client, registered):
    profile, _ = registered
    _fill(db, 1)
    save_profile(project, load_profile(project, profile.id).model_copy(
        update={"settings": {"no/such/setting": True}}))
    with db.session() as session:
        targets = build.plan(project, session, [profile.id], None, None)
    results = build.run(project, client, targets, dry_run=True)
    assert not results[0].ok
    assert any("no such setting" in d for d in results[0].details)
    assert not list(Path(project.output).glob("*.img"))


def test_dry_run_publishes_nothing(project, db, client, registered):
    profile, _ = registered
    _fill(db, 2)
    with db.session() as session:
        targets = build.plan(project, session, [profile.id], None, None)
    results = build.run(project, client, targets, dry_run=True)
    assert results[0].ok
    assert not list(Path(project.output).glob("*.img"))


def test_power_forced_and_default(project, db, client, registered):
    profile, info = registered
    levels = profile.power.levels
    if not levels:
        pytest.skip("model has no power levels")
    wires = [make_wire("146.520", name="NOPWR"), make_wire("146.540", name="W1", power_mw=1000)]
    with db.session(write=True) as session:
        catalog.import_memories(session, wires, "personal", "test")
    for power, expect_default in ((None, True), ("low", False), ("high", False)):
        with db.session() as session:
            targets = build.plan(project, session, [profile.id], None, None, power)
        result = build.run(project, client, targets, dry_run=True)[0]
        assert result.ok, result.details
        states = result.result["expected"]["memories"]
        lo = info["signature"]["memory_bounds"][0]
        first, second = states[str(lo)], states[str(lo + 1)]
        if expect_default:
            assert first["power_label"] == levels[profile.power.default]
        else:
            assert first["power_label"] == levels[power]
            assert second["power_label"] == levels[power]
