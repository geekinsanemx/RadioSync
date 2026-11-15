"""radiosync chirp_launcher: locate the CHIRP executable and open generated images in it.

Changelog:
- 0.1.12 (2026-11-14): initial version; system CHIRP lookup or explicit executable.
"""

import os
import shutil
import subprocess
from pathlib import Path

from .config import ConfigError, Project, RadiosyncError, chirp_python


def find_chirp(project: Project, executable: Path | None = None) -> Path:
    """Return the CHIRP executable: the given one, else PATH, else next to the CHIRP interpreter."""
    if executable is not None:
        path = executable.expanduser()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RadiosyncError(f"CHIRP executable not found or not executable: {path}")
        return path
    found = shutil.which("chirp")
    if found:
        return Path(found)
    try:
        sibling = chirp_python(project).parent / "chirp"
    except ConfigError:
        sibling = None
    if sibling is not None and sibling.is_file() and os.access(sibling, os.X_OK):
        return sibling
    raise RadiosyncError("CHIRP executable not found in PATH; use --exec <path>")


def launch(executable: Path, images: list[Path]) -> None:
    """Start CHIRP detached with the images; does not wait for it to exit."""
    try:
        subprocess.Popen([str(executable), *(str(image) for image in images)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        raise RadiosyncError(f"Could not start CHIRP ({executable}): {exc}") from exc
