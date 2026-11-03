"""radiosync build: compose sets per model, generate images in staging, publish with manifests.

Changelog:
- 0.1.8 (2026-11-01): optional frequency sort recorded in manifests.
- 0.1.6 (2026-11-01): compact content-hash output names and collision-safe reuse.
- 0.1.5 (2026-11-01): internal user storage; flat outputs in cwd or --output.
- 0.1.4 (2026-11-01): names longer than the model allows are shortened (name_fit).
- 0.1.2 (2026-11-01): optional forced power (low/mid/high) per build.
- 0.1.0 (2026-11-01): initial version.
"""

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from . import __version__
from .chirp_client import ChirpClient, ChirpWorkerError
from .composition import Composition, compose
from .config import Project, RadiosyncError, timestamp
from .names import fit_names
from .radios import RadioError, list_profiles, load_profile, sha256_file, verify_template
from .schemas import Preset, RadioProfile


class BuildError(RadiosyncError):
    pass


@dataclass
class BuildTarget:
    profile: RadioProfile
    composition: Composition
    power: str | None = None


@dataclass
class BuildResult:
    target: BuildTarget
    ok: bool
    error: str = ""
    details: list[str] = field(default_factory=list)
    result: dict | None = None
    image: Path | None = None
    manifest: Path | None = None
    template_sha: str = ""


def load_preset(project: Project, name: str) -> Preset:
    path = project.presets / f"{name}.json"
    if not path.is_file():
        known = ", ".join(p.stem for p in sorted(project.presets.glob("*.json"))) or "none"
        raise BuildError(f"Unknown preset {name!r}", [f"available: {known}"])
    try:
        return Preset.model_validate_json(path.read_text())
    except ValidationError as exc:
        raise BuildError(f"Preset {path.name} is invalid",
                         [f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                          for e in exc.errors()[:20]]) from exc


def plan(project: Project, session: Session, radio_ids: list[str],
         set_names: list[str] | None, preset_name: str | None,
         power: str | None = None, sort_by_frequency: bool = False) -> list[BuildTarget]:
    preset = load_preset(project, preset_name) if preset_name else None
    if preset and set_names:
        raise BuildError("Use either --sets or --preset, not both")
    if not radio_ids and preset and preset.radios:
        radio_ids = preset.radios
    if radio_ids:
        profiles = [load_profile(project, r) for r in dict.fromkeys(radio_ids)]
    else:
        profiles = [p for p in list_profiles(project) if p.enabled]
        if not profiles:
            raise BuildError("No enabled radios registered",
                             ["register one with 'radiosync radios register'"])
    selected = preset.sets if preset else set_names
    targets = []
    for profile in profiles:
        composition = compose(session, selected or profile.default_sets, sort_by_frequency)
        lo, hi = _bounds(project, profile)
        capacity = hi - lo + 1
        if len(composition.channels) > capacity:
            raise BuildError(f"{profile.id}: {len(composition.channels)} channels from sets "
                             f"{', '.join(composition.sets)} exceed {capacity} memories")
        if power is not None and power not in profile.power.levels:
            raise BuildError(f"{profile.id}: profile has no '{power}' power level",
                             [f"levels: {profile.power.levels}"])
        targets.append(BuildTarget(profile, composition, power))
    return targets


def _signature(project: Project, profile: RadioProfile) -> dict:
    path = project.templates / f"{profile.id}.signature.json"
    if not path.is_file():
        raise RadioError(f"Signature for {profile.id} is missing; register the template again")
    return json.loads(path.read_text())


def _bounds(project: Project, profile: RadioProfile) -> tuple[int, int]:
    lo, hi = _signature(project, profile)["memory_bounds"]
    return lo, hi


def fitted_wires(project: Project, profile: RadioProfile,
                 wires: list[dict]) -> tuple[list[dict], list[tuple[int, str, str]]]:
    """Copies of @wires with names fitted to the model; (index, before, after) per change."""
    wires = [dict(w) for w in wires]
    if not profile.name_fit:
        return wires, []
    signature = _signature(project, profile)
    names = [w["name"] for w in wires]
    changes = []
    fitted = fit_names(names, signature["valid_name_length"], signature["valid_characters"])
    for index, (wire, short) in enumerate(zip(wires, fitted)):
        if short != wire["name"]:
            changes.append((index, wire["name"], short))
            wire["name"] = short
    return wires, changes


def _ref(channel) -> str:
    return f"#{channel.memory_id} {channel.wire['name'] or '(no name)'}"


def _manifest(target: BuildTarget, result: dict, image: Path, template_sha: str,
              created: str) -> dict:
    by_ref = {_ref(c): c for c in target.composition.channels}
    channels = []
    for entry in result["channels"]:
        channel = by_ref[entry["ref"]]
        channels.append({"number": entry["number"], "memory_id": channel.memory_id,
                         "fingerprint": channel.fingerprint, "name": channel.wire["name"],
                         "sources": channel.sources})
    return {
        "format": "radiosync-manifest",
        "version": 1,
        "radio": target.profile.id,
        "created_at": created,
        "radiosync_version": __version__,
        "chirp_version": result["chirp_version"],
        "identity": result["identity"],
        "template_sha256": template_sha,
        "signature_sha256": target.profile.template.signature_sha256,
        "sets": target.composition.sets,
        "power": target.power,
        "sort": "frequency" if target.composition.sort_by_frequency else "sets",
        "image": {"file": image.name, "sha256": sha256_file(image), "size": image.stat().st_size},
        "channels": channels,
        "adaptations": result["adaptations"],
        "validation_warnings": result["validation_warnings"],
        "settings_applied": result["settings_applied"],
        "raw": result["raw"],
        "expected": result["expected"],
    }


def run(project: Project, client: ChirpClient, targets: list[BuildTarget],
        dry_run: bool, output: Path | None = None) -> list[BuildResult]:
    """Build every target in staging; publish all of them only if every build passed."""
    run_id = timestamp()
    destination = (output or Path.cwd()).expanduser().resolve()
    staging = Path(tempfile.mkdtemp(prefix="radiosync-build-"))
    results = []
    try:
        for target in targets:
            results.append(_build_one(project, client, target, staging, run_id))
        if dry_run or not all(r.ok for r in results):
            return results
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for item in results:
            _publish(destination, item, run_id, created)
        return results
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _build_one(project, client, target, staging, run_id) -> BuildResult:
    profile = target.profile
    try:
        template = verify_template(project, profile)
        output = staging / f"{profile.id}.img"
        channels = target.composition.channels
        wires, renamed = fitted_wires(project, profile, [c.wire for c in channels])
        lo = _bounds(project, profile)[0]
        result = client.build(
            template=str(template), output=str(output),
            identity=profile.identity.model_dump(),
            signature_sha256=profile.template.signature_sha256,
            profile=profile.worker_policy(target.power),
            channels=[{"ref": _ref(c), "wire": w} for c, w in zip(channels, wires)])
    except ChirpWorkerError as exc:
        return BuildResult(target, False, str(exc), exc.details)
    except RadiosyncError as exc:
        return BuildResult(target, False, str(exc), exc.details)
    result["adaptations"] = [
        {"number": lo + i, "ref": _ref(channels[i]), "kind": "name_fit", "before": before,
         "after": after} for i, before, after in renamed] + result["adaptations"]
    return BuildResult(target, True, result=result, image=output,
                       template_sha=profile.template.sha256)


def _same_output(image: Path, manifest: Path, expected: dict) -> bool:
    if not image.is_file() or not manifest.is_file():
        return False
    try:
        previous = json.loads(manifest.read_text())
        if not isinstance(previous, dict):
            return False
        previous.pop("created_at", None)
        comparable = {k: v for k, v in expected.items() if k != "created_at"}
        return previous == comparable and sha256_file(image) == expected["image"]["sha256"]
    except (OSError, ValueError):
        return False


def _publish(destination: Path, item: BuildResult, run_id: str, created: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    data = _manifest(item.target, item.result, item.image, item.template_sha, created)
    date = datetime.fromisoformat(created).strftime("%Y%m%d")
    base = f"{item.target.profile.id}_{date}_{data['image']['sha256'][:8]}"
    counter = 1
    while True:
        stem = base if counter == 1 else f"{base}_{counter}"
        image = destination / f"{stem}.img"
        manifest = destination / f"{stem}.manifest.json"
        data["image"]["file"] = image.name
        if image.exists() or manifest.exists():
            if _same_output(image, manifest, data):
                item.image, item.manifest = image, manifest
                return
            counter += 1
            continue
        try:
            handle = image.open("xb")
        except FileExistsError:
            counter += 1
            continue
        try:
            with handle, item.image.open("rb") as source:
                shutil.copyfileobj(source, handle)
            try:
                manifest_handle = manifest.open("x")
            except FileExistsError:
                image.unlink()
                counter += 1
                continue
            try:
                with manifest_handle:
                    json.dump(data, manifest_handle, indent=2)
                    manifest_handle.write("\n")
            except Exception:
                manifest.unlink(missing_ok=True)
                raise
        except Exception:
            image.unlink(missing_ok=True)
            raise
        item.image, item.manifest = image, manifest
        return
