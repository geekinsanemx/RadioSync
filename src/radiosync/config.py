"""radiosync config: project location, paths, CHIRP interpreter and backups.

Changelog:
- 0.1.5 (2026-11-01): internal user storage; flat outputs in cwd or --output.
- 0.1.1 (2026-11-01): project lookup via --home, RADIOSYNC_HOME, cwd, then the
  user default in ~/.config/radiosync/config.toml written by init.
- 0.1.0 (2026-11-01): initial version.
"""

import os
import shutil
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_FILE = Path("config.toml")

DEFAULT_PROJECT_TOML = """[paths]
database = "data/radiosync.db"
templates = "templates"
backups = "bkp"
radios = "radios"
presets = "presets"

[chirp]
"""

CHIRP_PYTHON_CANDIDATES = (
    "{pipx_home}/venvs/chirp/bin/python",
    "~/.local/share/pipx/venvs/chirp/bin/python",
    "~/.local/pipx/venvs/chirp/bin/python",
)


class RadiosyncError(Exception):
    """Base error with optional detail lines for the CLI."""

    def __init__(self, message, details=()):
        super().__init__(message)
        self.details = list(details)


class ConfigError(RadiosyncError):
    pass


@dataclass(frozen=True)
class Project:
    root: Path
    database: Path
    templates: Path
    output: Path
    backups: Path
    radios: Path
    presets: Path
    chirp_python_setting: str | None


def user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base).expanduser() / "radiosync" / "config.toml"


def storage_home(home: Path | None = None) -> Path:
    override = home or os.environ.get("RADIOSYNC_HOME")
    return Path(override).expanduser().resolve() if override else user_config_path().parent.resolve()


def find_root(start: Path | None = None, home: Path | None = None) -> Path:
    root = storage_home(home)
    path = root / PROJECT_FILE
    if not path.is_file():
        raise ConfigError(f"Storage is not initialized: {root}; run 'radiosync init'")
    with path.open("rb") as handle:
        if "home" in tomllib.load(handle):
            raise ConfigError("Legacy project pointer found; migrate the existing data before use")
    return root


def load_project(root: Path | None = None) -> Project:
    root = root or find_root()
    with open(root / PROJECT_FILE, "rb") as handle:
        data = tomllib.load(handle)
    paths = data.get("paths", {})

    def resolve(key, default):
        return (root / paths.get(key, default)).resolve()

    return Project(
        root=root,
        database=resolve("database", "data/radiosync.db"),
        templates=resolve("templates", "templates"),
        output=Path.cwd().resolve(),
        backups=resolve("backups", "bkp"),
        radios=resolve("radios", "radios"),
        presets=resolve("presets", "presets"),
        chirp_python_setting=data.get("chirp", {}).get("python"),
    )


def init_project(root: Path | None = None) -> Project:
    root = storage_home(root)
    config_file = root / PROJECT_FILE
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(DEFAULT_PROJECT_TOML)
    find_root(home=root)
    project = load_project(root)
    for path in (project.database.parent, project.templates,
                 project.backups, project.radios, project.presets):
        path.mkdir(parents=True, exist_ok=True)
    return project


def chirp_python(project: Project) -> Path:
    configured = os.environ.get("RADIOSYNC_CHIRP_PYTHON") or project.chirp_python_setting
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise ConfigError(f"CHIRP interpreter not found: {path}")
        return path
    pipx_home = os.environ.get("PIPX_HOME", "~/.local/share/pipx")
    for template in CHIRP_PYTHON_CANDIDATES:
        path = Path(template.format(pipx_home=pipx_home)).expanduser()
        if path.is_file():
            return path
    raise ConfigError("CHIRP interpreter not found; set [chirp] python in "
                      f"{PROJECT_FILE} or RADIOSYNC_CHIRP_PYTHON")


def timestamp() -> str:
    return datetime.now().strftime("%y%m%d%H%M%S")


def backup_target(project: Project, path: Path) -> Path:
    project.backups.mkdir(parents=True, exist_ok=True)
    base = project.backups / f"{path.name}.bkp-{timestamp()}"
    target = base
    counter = 1
    while target.exists():
        target = base.with_name(f"{base.name}-{counter}")
        counter += 1
    return target


def backup_file(project: Project, path: Path) -> Path | None:
    """Copy @path into the backup directory; None when @path does not exist."""
    if not path.exists():
        return None
    target = backup_target(project, path)
    shutil.copy2(path, target)
    return target
