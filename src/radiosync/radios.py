"""radiosync radios: per-model profiles and registered template images.

Changelog:
- 0.1.2 (2026-11-01): register fills low/mid/high power levels from the driver.
- 0.1.0 (2026-11-01): initial version.
"""

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from .chirp_client import ChirpClient
from .config import Project, RadiosyncError, backup_file
from .schemas import Identity, PowerPolicy, RadioProfile, TemplateInfo


class RadioError(RadiosyncError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slug(identity: dict) -> str:
    text = " ".join(p for p in (identity["vendor"], identity["model"], identity["variant"]) if p)
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def profile_path(project: Project, radio_id: str) -> Path:
    return project.radios / f"{radio_id}.json"


def template_path(project: Project, profile: RadioProfile) -> Path:
    return project.root / profile.template.file


def signature_path(project: Project, radio_id: str) -> Path:
    return project.templates / f"{radio_id}.signature.json"


def load_profile(project: Project, radio_id: str) -> RadioProfile:
    path = profile_path(project, radio_id)
    if not path.is_file():
        known = ", ".join(p.stem for p in sorted(project.radios.glob("*.json"))) or "none"
        raise RadioError(f"Unknown radio {radio_id!r}", [f"registered: {known}"])
    try:
        profile = RadioProfile.model_validate_json(path.read_text())
    except ValidationError as exc:
        raise RadioError(f"Profile {path.name} is invalid",
                         [f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                          for e in exc.errors()[:20]]) from exc
    if profile.id != radio_id:
        raise RadioError(f"Profile {path.name} declares id {profile.id!r}")
    return profile


def list_profiles(project: Project) -> list[RadioProfile]:
    return [load_profile(project, p.stem) for p in sorted(project.radios.glob("*.json"))]


def save_profile(project: Project, profile: RadioProfile) -> Path | None:
    path = profile_path(project, profile.id)
    backup = backup_file(project, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile.model_dump_json(indent=2) + "\n")
    return backup


def verify_template(project: Project, profile: RadioProfile) -> Path:
    path = template_path(project, profile)
    if not path.is_file():
        raise RadioError(f"Template for {profile.id} is missing: {profile.template.file}")
    if sha256_file(path) != profile.template.sha256:
        raise RadioError(f"Template for {profile.id} changed since it was registered",
                         ["register it again with 'radiosync radios register --replace'"])
    return path


def default_power_levels(levels: list[list]) -> dict[str, str]:
    """low = lowest watts, high = highest, mid = middle level, or low when there are two."""
    ordered = [label for label, _ in sorted(levels, key=lambda item: item[1])]
    if not ordered:
        return {}
    mid = ordered[len(ordered) // 2] if len(ordered) >= 3 else ordered[0]
    return {"low": ordered[0], "mid": mid, "high": ordered[-1]}


def _check_power(power: PowerPolicy, levels: list[list]) -> list[str]:
    labels = {label for label, _ in levels}
    return [f"power {name} -> {label!r} is not a level of this model"
            for name, label in power.levels.items() if label not in labels]


def _check_settings(overrides: dict, described: list[dict]) -> list[str]:
    usable = {d["path"] for d in described if d["overridable"] and d["mutable"]}
    return [f"setting {p!r} is not available or not writable" for p in overrides
            if p not in usable]


def register(project: Project, client: ChirpClient, source: Path,
             radio_id: str | None = None, replace: bool = False) -> tuple[RadioProfile, dict, list[Path]]:
    """Copy @source as the template of a model and create or refresh its profile."""
    if not source.is_file():
        raise RadioError(f"Template not found: {source}")
    info = client.inspect(source)
    identity = Identity(**info["identity"])
    radio_id = radio_id or slug(info["identity"])
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", radio_id):
        raise RadioError(f"Invalid radio id {radio_id!r}")
    existing = None
    if profile_path(project, radio_id).exists():
        if not replace:
            raise RadioError(f"Radio {radio_id!r} is already registered",
                             ["use --replace to change its template"])
        existing = load_profile(project, radio_id)
        if existing.identity != identity:
            raise RadioError(f"Template is a {identity.vendor} {identity.model}, "
                             f"profile {radio_id!r} is a {existing.identity.vendor} "
                             f"{existing.identity.model}")
    template_extras = {e["name"]: e["value"] for e in info["extras"]}
    if existing is not None:
        problems = _check_settings(existing.settings, info["settings"])
        unknown = sorted(set(existing.extras) - set(template_extras))
        problems += [f"extra {name!r} no longer offered" for name in unknown]
        problems += _check_power(existing.power, info["signature"]["valid_power_levels"])
        if problems:
            raise RadioError("Existing profile does not fit the new template", problems)
        extras = {**template_extras, **existing.extras}
    else:
        extras = template_extras

    dest = project.templates / f"{radio_id}.img"
    sig_file = signature_path(project, radio_id)
    backups = [b for b in (backup_file(project, dest), backup_file(project, sig_file)) if b]
    project.templates.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    sig_file.write_text(json.dumps(info["signature"], indent=2, sort_keys=True) + "\n")
    template = TemplateInfo(
        file=str(dest.relative_to(project.root)),
        sha256=sha256_file(dest),
        signature_sha256=info["signature_sha256"],
        chirp_version=info["chirp_version"],
        registered_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    if existing is not None:
        profile = existing.model_copy(update={"template": template, "extras": extras})
    else:
        power = PowerPolicy(levels=default_power_levels(info["signature"]["valid_power_levels"]))
        profile = RadioProfile(id=radio_id, identity=identity, template=template, extras=extras,
                               power=power)
    profile_backup = save_profile(project, profile)
    if profile_backup:
        backups.append(profile_backup)
    return profile, info, backups
