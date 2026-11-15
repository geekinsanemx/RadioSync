"""CHIRP executable lookup and detached launch tests."""

import subprocess
from pathlib import Path

import pytest

from radiosync import chirp_launcher
from radiosync.config import ConfigError, RadiosyncError


def make_exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def no_path(monkeypatch):
    monkeypatch.setattr(chirp_launcher.shutil, "which", lambda name: None)


def test_explicit_executable(tmp_path):
    exe = make_exe(tmp_path / "bin" / "chirp")
    assert chirp_launcher.find_chirp(None, exe) == exe


def test_explicit_missing(tmp_path):
    with pytest.raises(RadiosyncError, match="not found"):
        chirp_launcher.find_chirp(None, tmp_path / "missing")


def test_explicit_not_executable(tmp_path):
    path = tmp_path / "chirp"
    path.write_text("")
    path.chmod(0o644)
    with pytest.raises(RadiosyncError, match="not executable"):
        chirp_launcher.find_chirp(None, path)


def test_system_path(monkeypatch, tmp_path):
    exe = make_exe(tmp_path / "chirp")
    monkeypatch.setattr(chirp_launcher.shutil, "which", lambda name: str(exe))
    assert chirp_launcher.find_chirp(None) == exe


def test_next_to_interpreter(monkeypatch, tmp_path, no_path):
    python = make_exe(tmp_path / "venv" / "bin" / "python")
    exe = make_exe(tmp_path / "venv" / "bin" / "chirp")
    monkeypatch.setattr(chirp_launcher, "chirp_python", lambda project: python)
    assert chirp_launcher.find_chirp(None) == exe


def test_not_found(monkeypatch, no_path):
    def missing(project):
        raise ConfigError("CHIRP interpreter not found")
    monkeypatch.setattr(chirp_launcher, "chirp_python", missing)
    with pytest.raises(RadiosyncError, match="--exec"):
        chirp_launcher.find_chirp(None)


def test_launch_detached(monkeypatch, tmp_path):
    calls = []

    class FakePopen:
        def __init__(self, args, **kwargs):
            calls.append((args, kwargs))

        def wait(self):
            raise AssertionError("launch must not wait for CHIRP")

    monkeypatch.setattr(chirp_launcher.subprocess, "Popen", FakePopen)
    images = [tmp_path / "a.img", tmp_path / "b.img"]
    chirp_launcher.launch(Path("/opt/chirp"), images)
    args, kwargs = calls[0]
    assert args == ["/opt/chirp", str(images[0]), str(images[1])]
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL


def test_launch_error(monkeypatch):
    def broken(*args, **kwargs):
        raise PermissionError("denied")
    monkeypatch.setattr(chirp_launcher.subprocess, "Popen", broken)
    with pytest.raises(RadiosyncError, match="Could not start CHIRP"):
        chirp_launcher.launch(Path("/opt/chirp"), [Path("x.img")])
