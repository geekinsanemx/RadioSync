"""radiosync tests: build planning (radio selection, sets, presets, capacity).

Changelog:
- 0.1.2 (2026-11-01): power level selection.
- 0.1.0 (2026-11-01): initial version.
"""

import json

import pytest

from radiosync import build, catalog
from radiosync.radios import default_power_levels, save_profile
from radiosync.schemas import Identity, RadioProfile, TemplateInfo

from .conftest import make_wire


def _profile(project, radio_id, bounds, enabled=True, default_sets=("personal",)):
    profile = RadioProfile(
        id=radio_id, enabled=enabled, default_sets=list(default_sets),
        identity=Identity(vendor="V", model=radio_id, rclass="R"),
        template=TemplateInfo(file=f"templates/{radio_id}.img", sha256="0", signature_sha256="0",
                              chirp_version="test", registered_at="now"))
    save_profile(project, profile)
    (project.templates / f"{radio_id}.signature.json").write_text(
        json.dumps({"memory_bounds": list(bounds)}))
    return profile


def _memories(db, set_name, count):
    with db.session(write=True) as session:
        catalog.import_memories(session, [make_wire(f"{146 + i / 1000:.3f}") for i in range(count)],
                                set_name, "x")


def test_plan_defaults_and_disabled(project, db):
    _profile(project, "big", (1, 1000))
    _profile(project, "off", (1, 1000), enabled=False)
    _memories(db, "personal", 3)
    with db.session() as session:
        targets = build.plan(project, session, [], None, None)
    assert [t.profile.id for t in targets] == ["big"]
    assert len(targets[0].composition.channels) == 3


def test_plan_capacity_error(project, db):
    _profile(project, "small", (0, 4))
    _memories(db, "personal", 6)
    with db.session() as session:
        with pytest.raises(build.BuildError, match="exceed 5 memories"):
            build.plan(project, session, ["small"], None, None)


def test_plan_preset(project, db):
    _profile(project, "a", (1, 100))
    _profile(project, "b", (1, 100))
    _memories(db, "personal", 1)
    _memories(db, "scanner", 2)
    (project.presets / "p.json").write_text(json.dumps({"sets": ["scanner", "personal"],
                                                        "radios": ["b"]}))
    with db.session() as session:
        targets = build.plan(project, session, [], None, "p")
        assert [t.profile.id for t in targets] == ["b"]
        assert targets[0].composition.sets == ["personal", "scanner"]
        with pytest.raises(build.BuildError):
            build.plan(project, session, [], ["personal"], "p")


def test_default_power_levels():
    assert default_power_levels([["High", 5000], ["Low", 1000]]) == \
        {"low": "Low", "mid": "Low", "high": "High"}
    assert default_power_levels([["Low", 1000], ["Medium", 2500], ["High", 5000]]) == \
        {"low": "Low", "mid": "Medium", "high": "High"}
    assert default_power_levels([]) == {}


def test_plan_power_needs_level(project, db):
    _profile(project, "nopower", (1, 100))
    _memories(db, "personal", 1)
    with db.session() as session:
        with pytest.raises(build.BuildError, match="no 'low' power level"):
            build.plan(project, session, ["nopower"], None, None, "low")


def publication_item(tmp_path):
    from types import SimpleNamespace
    from radiosync.composition import Composition
    profile = SimpleNamespace(id="test-radio", template=SimpleNamespace(signature_sha256="sig"))
    target = build.BuildTarget(profile, Composition(["personal"], []))
    source = tmp_path / "staging.img"
    source.write_bytes(b"test radio image")
    result = {"channels": [], "chirp_version": "test", "identity": {}, "adaptations": [],
              "validation_warnings": [], "settings_applied": {}, "raw": {}, "expected": {}}
    return build.BuildResult(target, True, result=result, image=source, template_sha="template")


def test_short_output_name_and_hash(tmp_path):
    import hashlib
    item = publication_item(tmp_path)
    destination = tmp_path / "out"
    short = hashlib.sha256(item.image.read_bytes()).hexdigest()[:8]
    build._publish(destination, item, "unused", "2026-11-01T12:00:00+00:00")
    assert item.image.name == f"test-radio_20261101_{short}.img"
    assert item.manifest.parent == destination
    assert json.loads(item.manifest.read_text())["image"]["file"] == item.image.name


def test_identical_output_reused(tmp_path):
    destination = tmp_path / "out"
    item = publication_item(tmp_path)
    build._publish(destination, item, "unused", "2026-11-01T12:00:00+00:00")
    before = item.manifest.read_bytes(), item.image.stat().st_mtime_ns
    repeat = publication_item(tmp_path)
    build._publish(destination, repeat, "unused", "2026-11-01T13:00:00+00:00")
    assert repeat.image == item.image
    assert before == (repeat.manifest.read_bytes(), repeat.image.stat().st_mtime_ns)
    assert len(list(destination.iterdir())) == 2


@pytest.mark.parametrize("collision", ["content", "details", "missing-manifest", "invalid-manifest"])
def test_output_collision_preserves_previous_files(tmp_path, collision):
    destination = tmp_path / "out"
    item = publication_item(tmp_path)
    build._publish(destination, item, "unused", "2026-11-01T12:00:00+00:00")
    repeat = publication_item(tmp_path)
    if collision == "content":
        item.image.write_bytes(b"unrelated image")
    elif collision == "details":
        repeat.target.power = "low"
    elif collision == "missing-manifest":
        item.manifest.unlink()
    else:
        item.manifest.write_text("not JSON")
    preserved = {p.name: p.read_bytes() for p in destination.iterdir()}
    build._publish(destination, repeat, "unused", "2026-11-01T13:00:00+00:00")
    assert repeat.image.stem == item.image.stem + "_2"
    assert all((destination / name).read_bytes() == data for name, data in preserved.items())


def test_plan_records_frequency_sort(project, db):
    _profile(project, "sorted", (1, 100))
    _memories(db, "personal", 3)
    with db.session() as session:
        targets = build.plan(project, session, ["sorted"], None, None, sort_by_frequency=True)
    assert targets[0].composition.sort_by_frequency
