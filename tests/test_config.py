"""Configuration storage isolation tests."""

import pytest

from radiosync.config import ConfigError, find_root, init_project, load_project, storage_home


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("RADIOSYNC_HOME", raising=False)


def test_storage_independent_of_cwd(tmp_path, monkeypatch):
    default = init_project()
    assert default.root == tmp_path / "xdg" / "radiosync"
    local = init_project(tmp_path / "other")
    monkeypatch.chdir(local.root)
    assert find_root() == default.root
    assert find_root(home=local.root) == local.root
    monkeypatch.setenv("RADIOSYNC_HOME", str(local.root))
    assert find_root() == local.root
    assert find_root(home=default.root) == default.root
    assert load_project().output == local.root


def test_invalid_home_rejected(tmp_path):
    with pytest.raises(ConfigError):
        find_root(home=tmp_path / "missing")


def test_legacy_pointer_not_silently_used(tmp_path):
    root = storage_home()
    root.mkdir(parents=True)
    (root / "config.toml").write_text('home = "/path/to/old"\n')
    with pytest.raises(ConfigError, match="Legacy"):
        find_root()
