"""radiosync settings: export, compare and import radio settings for a model profile.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

from pathlib import Path

from .chirp_client import ChirpClient
from .config import Project
from .radios import RadioError, load_profile, save_profile, verify_template


def export_settings(project: Project, client: ChirpClient, radio_id: str) -> dict:
    profile = load_profile(project, radio_id)
    info = client.inspect(verify_template(project, profile))
    return {
        "radio": radio_id,
        "identity": info["identity"],
        "chirp_version": info["chirp_version"],
        "overrides": profile.settings,
        "settings": info["settings"],
        "extras": info["extras"],
    }


def diff_image(project: Project, client: ChirpClient, radio_id: str, image: Path) -> list[dict]:
    """Settings where @image differs from the template, with the current profile value."""
    profile = load_profile(project, radio_id)
    template = verify_template(project, profile)
    if not image.is_file():
        raise RadioError(f"Image not found: {image}")
    differences = client.settings_diff(template, image)
    for entry in differences:
        entry["profile"] = profile.settings.get(entry["path"])
    return differences


def import_from_image(project: Project, client: ChirpClient, radio_id: str, image: Path,
                      dry_run: bool) -> tuple[dict, list[dict], list[dict], Path | None]:
    """Replace the profile overrides with the writable settings in which @image differs."""
    profile = load_profile(project, radio_id)
    differences = diff_image(project, client, radio_id, image)
    usable = [d for d in differences if d["mutable"] and d["overridable"]]
    skipped = [d for d in differences if not (d["mutable"] and d["overridable"])]
    overrides = {d["path"]: d["image"] for d in usable}
    backup = None
    if not dry_run:
        backup = save_profile(project, profile.model_copy(update={"settings": overrides}))
    return overrides, usable, skipped, backup
