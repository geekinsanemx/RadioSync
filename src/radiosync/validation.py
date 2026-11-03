"""radiosync validation: re-check published images against their manifests before upload.

Changelog:
- 0.1.5 (2026-11-01): internal user storage; flat outputs in cwd or --output.
- 0.1.0 (2026-11-01): initial version.
"""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .chirp_client import ChirpClient, ChirpWorkerError
from .config import Project, RadiosyncError
from .radios import sha256_file
from .schemas import Manifest


class ValidationFailed(RadiosyncError):
    pass


@dataclass
class ValidationResult:
    manifest: Path
    image: Path | None
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def latest_manifests(project: Project, radio_ids: list[str] | None,
                     output: Path | None = None) -> list[Path]:
    folder = (output or Path.cwd()).expanduser().resolve()
    latest = {}
    for path in folder.glob("*.manifest.json"):
        try:
            manifest = Manifest.model_validate_json(path.read_text())
        except (ValidationError, ValueError):
            raise ValidationFailed(f"Invalid manifest: {path}")
        radio = manifest.radio
        if radio_ids and radio not in radio_ids:
            continue
        if radio not in latest or path.stat().st_mtime_ns > latest[radio].stat().st_mtime_ns:
            latest[radio] = path
    missing = set(radio_ids or []) - latest.keys()
    if missing:
        raise ValidationFailed(f"No generated images for: {', '.join(sorted(missing))}")
    if not latest:
        raise ValidationFailed(f"No manifests found in {folder}")
    return [latest[key] for key in sorted(latest)]


def validate(client: ChirpClient, manifest_path: Path) -> ValidationResult:
    try:
        manifest = Manifest.model_validate_json(manifest_path.read_text())
    except (ValidationError, ValueError) as exc:
        return ValidationResult(manifest_path, None, [f"manifest unreadable: {exc}"])
    image = manifest_path.with_name(manifest.image.file)
    result = ValidationResult(manifest_path, image)
    if not image.is_file():
        result.problems.append(f"image {image.name} is missing")
        return result
    if image.stat().st_size != manifest.image.size:
        result.problems.append(f"size {image.stat().st_size} differs from {manifest.image.size}")
    if sha256_file(image) != manifest.image.sha256:
        result.problems.append("SHA-256 differs from the manifest: the file was modified")
    try:
        verified = client.verify(image, manifest.identity.model_dump(), manifest.expected)
    except ChirpWorkerError as exc:
        result.problems.append(f"CHIRP could not load the image: {exc}")
        result.problems.extend(exc.details)
        return result
    result.problems.extend(verified["problems"])
    if verified["chirp_version"] != manifest.chirp_version:
        result.notes.append(f"built with CHIRP {manifest.chirp_version}, "
                            f"checked with {verified['chirp_version']}")
    return result
