"""radiosync chirp_worker: CHIRP driver operations, run with the CHIRP interpreter.

Reads one JSON request from stdin and writes one JSON response to stdout.
Never opens serial ports; only reads images/CSV and writes new files.

Changelog:
- 0.1.2 (2026-11-01): power from forced low/mid/high, channel watts, or profile default.
- 0.1.0 (2026-11-01): initial version.
"""

import copy
import gettext
import hashlib
import importlib.util
import json
import logging
import sys
import traceback
import warnings
from pathlib import Path


def _load_rules():
    path = Path(__file__).with_name("memory_rules.py")
    spec = importlib.util.spec_from_file_location("radiosync_memory_rules", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = _load_rules()
gettext.install("CHIRP")
warnings.simplefilter("ignore", FutureWarning)

from chirp import CHIRP_VERSION, chirp_common, directory, errors, import_logic, settings
from chirp.drivers import generic_csv

directory.import_drivers()


class WorkerError(Exception):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or []


class LogCollector(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append(f"{record.levelname} {record.name}: {record.getMessage()}")


def identity(radio):
    rclass = getattr(radio, "_orig_rclass", type(radio))
    return {
        "vendor": radio.VENDOR,
        "model": radio.MODEL,
        "variant": radio.VARIANT or "",
        "rclass": rclass.__name__,
    }


def load_image(path):
    radio = directory.get_radio_by_image(str(path))
    if not isinstance(radio, chirp_common.CloneModeRadio):
        raise WorkerError(f"{Path(path).name} is not a clone-mode radio image")
    return radio


def stripped_bytes(radio, path):
    data = Path(path).read_bytes()
    return type(radio)._strip_metadata(data)[0]


def value_type(value):
    if isinstance(value, settings.RadioSettingValueBoolean):
        return "boolean"
    if isinstance(value, settings.RadioSettingValueInteger):
        return "integer"
    if isinstance(value, settings.RadioSettingValueFloat):
        return "float"
    if isinstance(value, settings.RadioSettingValueList):
        return "list"
    if isinstance(value, settings.RadioSettingValueString):
        return "string"
    return "other"


def value_to_json(value):
    if not value.initialized:
        return None
    kind = value_type(value)
    raw = value.get_value()
    if kind == "boolean":
        return bool(raw)
    if kind == "integer":
        return int(raw)
    if kind == "float":
        return float(raw)
    return str(raw)


def describe_value(value):
    kind = value_type(value)
    info = {"type": kind}
    if kind == "integer":
        info.update(min=value.get_min(), max=value.get_max(), step=value.get_step())
    elif kind == "float":
        info.update(min=value.get_min(), max=value.get_max())
    elif kind == "list":
        info["options"] = [str(o) for o in value.get_options()]
    elif kind == "string":
        info.update(minlength=value.minlength, maxlength=value.maxlength)
    return info


def setting_json(rs):
    values = list(rs)
    if len(values) == 1:
        return value_to_json(values[0])
    return [value_to_json(v) for v in values]


def apply_json(value, target, label):
    kind = value_type(value)
    if kind == "boolean":
        if not isinstance(target, bool):
            raise WorkerError(f"{label}: expected true/false, got {target!r}")
    elif kind == "integer":
        if isinstance(target, bool) or not isinstance(target, int):
            raise WorkerError(f"{label}: expected integer, got {target!r}")
        lo, hi, step = value.get_min(), value.get_max(), value.get_step()
        if not lo <= target <= hi or (target - lo) % step:
            raise WorkerError(f"{label}: {target} outside {lo}..{hi} step {step}")
    elif kind == "float":
        if isinstance(target, bool) or not isinstance(target, (int, float)):
            raise WorkerError(f"{label}: expected number, got {target!r}")
        if not value.get_min() <= target <= value.get_max():
            raise WorkerError(f"{label}: {target} outside {value.get_min()}..{value.get_max()}")
    elif kind == "list":
        options = [str(o) for o in value.get_options()]
        if not isinstance(target, str) or target not in options:
            raise WorkerError(f"{label}: {target!r} is not one of {options}")
    elif kind == "string":
        if not isinstance(target, str):
            raise WorkerError(f"{label}: expected text, got {target!r}")
    else:
        raise WorkerError(f"{label}: unsupported setting type {type(value).__name__}")
    try:
        value.set_value(target)
    except (settings.InvalidValueError, ValueError) as exc:
        raise WorkerError(f"{label}: {exc}") from exc


def apply_setting_json(rs, target, label):
    values = list(rs)
    if len(values) == 1:
        targets = [target]
    elif isinstance(target, list) and len(target) == len(values):
        targets = target
    else:
        raise WorkerError(f"{label}: expected a list of {len(values)} values")
    for value, item in zip(values, targets):
        if not value.get_mutable():
            raise WorkerError(f"{label}: setting is read-only")
        if not value.initialized:
            raise WorkerError(f"{label}: setting is not initialized in this image")
        apply_json(value, item, label)


def walk_settings(group, prefix=()):
    elements = group if isinstance(group, list) else group.values()
    for element in elements:
        if isinstance(element, settings.RadioSetting):
            yield "/".join(prefix + (element.get_name(),)), element
        elif isinstance(element, settings.RadioSettingGroup):
            yield from walk_settings(element, prefix + (element.get_name(),))


def index_settings(tree):
    index = {}
    keyed = {}
    duplicates = set()
    for path, rs in walk_settings(tree):
        if path in index:
            duplicates.add(path)
            n = 2
            while f"{path}#{n}" in keyed:
                n += 1
            keyed[f"{path}#{n}"] = rs
        else:
            index[path] = rs
            keyed[path] = rs
    return index, keyed, duplicates


def settings_snapshot(radio):
    _, keyed, _ = index_settings(radio.get_settings())
    return {key: setting_json(rs) for key, rs in keyed.items()}


def describe_settings(radio):
    _, keyed, duplicates = index_settings(radio.get_settings())
    result = []
    for key, rs in keyed.items():
        values = list(rs)
        entry = {
            "path": key,
            "label": rs.get_shortname(),
            "value": setting_json(rs),
            "mutable": all(v.get_mutable() for v in values),
            "initialized": all(v.initialized for v in values),
            "overridable": key not in duplicates and "#" not in key,
        }
        entry.update(describe_value(values[0]))
        if len(values) > 1:
            entry["count"] = len(values)
        doc = getattr(rs, "__doc__", None)
        if doc:
            entry["doc"] = str(doc)
        result.append(entry)
    return result


def remove_dead_settings(root):
    for element in list(root.values()):
        if isinstance(element, settings.RadioSetting):
            if any(not v.get_mutable() or not v.initialized for v in element):
                del root[element]
        elif isinstance(element, settings.RadioSettingGroup):
            remove_dead_settings(element)


def apply_setting_overrides(radio, overrides, acknowledged):
    tree = radio.get_settings()
    index, _, duplicates = index_settings(tree)
    problems = []
    expected = {}
    changed = False
    for path, target in overrides.items():
        if path in duplicates:
            problems.append(f"{path}: name is not unique in this driver, cannot be set")
            continue
        rs = index.get(path)
        if rs is None:
            problems.append(f"{path}: no such setting for this model")
            continue
        before = setting_json(rs)
        try:
            apply_setting_json(rs, target, path)
        except WorkerError as exc:
            problems.append(str(exc))
            continue
        after = setting_json(rs)
        expected[path] = after
        if after != before:
            changed = True
            warning = rs.get_warning(list(rs)[0].get_value())
            if warning and path not in acknowledged:
                problems.append(f"{path}: driver warning must be acknowledged: {warning}")
    if problems:
        raise WorkerError("Settings could not be applied", problems)
    if changed:
        payload = copy.deepcopy(tree)
        for group in payload:
            remove_dead_settings(group)
        radio.set_settings(payload)
    return expected, changed


def extras_json(mem):
    return {rs.get_name(): setting_json(rs) for rs in (mem.extra or [])}


def mem_to_wire(mem):
    power_mw = None
    if mem.power is not None:
        power_mw = round(chirp_common.dBm_to_watts(float(mem.power)) * 1000)
    return {
        "freq_hz": int(mem.freq),
        "duplex": mem.duplex,
        "offset_hz": int(mem.offset),
        "mode": mem.mode,
        "tmode": mem.tmode,
        "rtone_dhz": round(float(mem.rtone) * 10),
        "ctone_dhz": round(float(mem.ctone) * 10),
        "dtcs": int(mem.dtcs),
        "rx_dtcs": int(mem.rx_dtcs),
        "dtcs_polarity": mem.dtcs_polarity,
        "cross_mode": mem.cross_mode,
        "name": (mem.name or "").rstrip(),
        "comment": mem.comment or "",
        "skip": mem.skip or "",
        "power_mw": power_mw,
        "tuning_step_hz": round(float(mem.tuning_step) * 1000),
    }


def mem_state(mem):
    if mem.empty:
        return {"empty": True}
    state = mem_to_wire(mem)
    state["empty"] = False
    state["power_label"] = None if mem.power is None else str(mem.power)
    state["extra"] = extras_json(mem)
    return state


def wire_to_mem(wire, number):
    mem = chirp_common.Memory()
    mem.number = number
    mem.freq = int(wire["freq_hz"])
    mem.duplex = wire["duplex"]
    mem.offset = int(wire["offset_hz"])
    mem.mode = wire["mode"]
    mem.tmode = wire["tmode"]
    mem.rtone = wire["rtone_dhz"] / 10
    mem.ctone = wire["ctone_dhz"] / 10
    mem.dtcs = int(wire["dtcs"])
    mem.rx_dtcs = int(wire["rx_dtcs"])
    mem.dtcs_polarity = wire["dtcs_polarity"]
    mem.cross_mode = wire["cross_mode"]
    mem.name = wire["name"]
    mem.comment = wire["comment"]
    mem.skip = wire["skip"]
    if wire.get("power_mw") is not None:
        mem.power = chirp_common.AutoNamedPowerLevel(wire["power_mw"] / 1000)
    if wire.get("tuning_step_hz") is not None:
        mem.tuning_step = wire["tuning_step_hz"] / 1000
    return mem


def canonical_wire(mem, keep_step=True):
    wire = rules.canonical(mem_to_wire(mem))
    if not keep_step:
        wire["tuning_step_hz"] = None
    wire["fingerprint"] = rules.fingerprint(wire)
    return wire


def read_memory(radio, number):
    mem = radio.get_memory(number)
    if hasattr(radio, "get_memory_extra"):
        mem = radio.get_memory_extra(mem)
    return mem


def signature(radio):
    rf = radio.get_features()
    lo, hi = rf.memory_bounds
    extras = []
    for number in range(lo, hi + 1):
        mem = radio.get_memory(number)
        if not mem.empty:
            extras = [[rs.get_name(), value_type(list(rs)[0])] for rs in (mem.extra or [])]
            break
    _, keyed, _ = index_settings(radio.get_settings())
    return {
        "identity": identity(radio),
        "memory_bounds": [lo, hi],
        "valid_name_length": rf.valid_name_length,
        "valid_characters": rf.valid_characters,
        "valid_power_levels": [[str(p), round(chirp_common.dBm_to_watts(float(p)) * 1000)]
                               for p in rf.valid_power_levels],
        "valid_modes": list(rf.valid_modes),
        "valid_tmodes": list(rf.valid_tmodes),
        "valid_duplexes": list(rf.valid_duplexes),
        "valid_cross_modes": list(rf.valid_cross_modes),
        "valid_skips": list(rf.valid_skips),
        "valid_tuning_steps": list(rf.valid_tuning_steps),
        "valid_bands": [list(b) for b in rf.valid_bands],
        "valid_special_chans": list(rf.valid_special_chans),
        "valid_tones": list(rf.valid_tones),
        "valid_dtcs_codes": list(rf.valid_dtcs_codes),
        "valid_dtcs_pols": list(rf.valid_dtcs_pols),
        "flags": {name: bool(getattr(rf, name)) for name in (
            "has_ctone", "has_rx_dtcs", "has_comment", "has_bank", "has_settings",
            "has_variable_power", "has_sub_devices", "has_tuning_step", "can_odd_split")},
        "extras": extras,
        "settings": [[key, value_type(list(rs)[0])] for key, rs in keyed.items()],
    }


def signature_sha256(sig):
    return hashlib.sha256(json.dumps(sig, sort_keys=True).encode()).hexdigest()


def op_inspect(req):
    radio = load_image(req["path"])
    rf = radio.get_features()
    lo, hi = rf.memory_bounds
    extras = []
    extras_source = None
    for number in range(lo, hi + 1):
        mem = radio.get_memory(number)
        if not mem.empty:
            extras_source = number
            for rs in mem.extra or []:
                entry = {"name": rs.get_name(), "label": rs.get_shortname(),
                         "value": setting_json(rs)}
                entry.update(describe_value(list(rs)[0]))
                extras.append(entry)
            break
    used = sum(1 for n in range(lo, hi + 1) if not radio.get_memory(n).empty)
    sig = signature(radio)
    return {
        "identity": identity(radio),
        "chirp_version": CHIRP_VERSION,
        "signature": sig,
        "signature_sha256": signature_sha256(sig),
        "memories_used": used,
        "extras": extras,
        "extras_source": extras_source,
        "settings": describe_settings(radio),
    }


def csv_precheck(path):
    import csv
    problems = []
    rows = 0
    header = None
    locations = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for lineno, line in enumerate(csv.reader(handle), start=1):
            if line and line[0].startswith("#"):
                continue
            if header is None:
                header = line
                unknown = [f for f in header if f not in chirp_common.Memory.CSV_FORMAT]
                if unknown:
                    problems.append(f"Unknown CSV columns: {', '.join(unknown)}")
                if "Frequency" not in header or "Location" not in header:
                    problems.append("CSV must have Location and Frequency columns")
                continue
            rows += 1
            if "Location" in header and len(line) == len(header):
                loc = line[header.index("Location")].strip()
                if loc in locations:
                    problems.append(f"Line {lineno}: Location {loc} repeats line {locations[loc]}")
                else:
                    locations[loc] = lineno
    return rows, problems


def op_read_channels(req):
    path = Path(req["path"])
    if path.suffix.lower() == ".csv":
        rows, problems = csv_precheck(path)
        if problems:
            raise WorkerError("CSV file rejected", problems)
        radio = generic_csv.CSVRadio(str(path))
        if radio.errors:
            raise WorkerError("CSV file rejected", list(radio.errors))
        source = {"type": "csv", "rows": rows}
        mems = [m for m in radio.memories if not m.empty]
        if len(mems) != rows:
            raise WorkerError("CSV file rejected",
                              [f"{rows - len(mems)} rows have no frequency or no Location"])
    else:
        radio = load_image(path)
        rf = radio.get_features()
        lo, hi = rf.memory_bounds
        mems = [m for m in (read_memory(radio, n) for n in range(lo, hi + 1)) if not m.empty]
        source = {"type": "image", "identity": identity(radio)}
    out = []
    problems = []
    for mem in mems:
        if isinstance(mem, chirp_common.DVMemory) or mem.mode == "DV":
            problems.append(f"Location {mem.number}: D-STAR memories are not supported")
            continue
        wire = canonical_wire(mem)
        wire["location"] = mem.number
        out.append(wire)
    if problems:
        raise WorkerError("File rejected", problems)
    return {"source": source, "memories": out}


def op_normalize(req):
    out = []
    problems = []
    for index, wire in enumerate(req["memories"]):
        try:
            mem = wire_to_mem(wire, 0)
            result = canonical_wire(mem, keep_step=wire.get("tuning_step_hz") is not None)
        except (ValueError, KeyError, TypeError) as exc:
            problems.append({"index": index, "error": str(exc)})
            continue
        out.append(result)
    if problems:
        raise WorkerError("Invalid memory values", problems)
    return {"memories": out}


def op_write_csv(req):
    radio = generic_csv.CSVRadio(None)
    radio.erase_memory(0)
    for number, wire in enumerate(req["memories"], start=1):
        radio.set_memory(wire_to_mem(wire, number))
    radio.save(req["path"])
    return {"written": len(req["memories"])}


def classify_name(src_name, dst_name, rf):
    original = src_name.rstrip()
    if original == dst_name.rstrip():
        return []
    kinds = []
    upper_only = rf.valid_characters == rf.valid_characters.upper()
    candidate = original.upper() if upper_only else original
    if upper_only and original != candidate:
        kinds.append("name_case")
    if len(candidate) > rf.valid_name_length:
        kinds.append("name_length")
    if any(c not in rf.valid_characters for c in candidate):
        kinds.append("name_chars")
    return kinds or ["name_other"]


def adaptation_kinds(src, dst, rf):
    found = []
    for kind in classify_name(src.name, dst.name, rf):
        found.append((kind, src.name.rstrip(), dst.name.rstrip()))
    pairs = {
        "power": (str(src.power), str(dst.power)),
        "tone": ((src.rtone, src.ctone), (dst.rtone, dst.ctone)),
        "dtcs": ((src.dtcs, src.rx_dtcs), (dst.dtcs, dst.rx_dtcs)),
        "mode": (src.mode, dst.mode),
        "duplex": ((src.duplex, src.offset), (dst.duplex, dst.offset)),
        "tuning_step": (src.tuning_step, dst.tuning_step),
        "other": ((src.freq, src.tmode, src.cross_mode, src.dtcs_polarity, src.skip,
                   src.comment),
                  (dst.freq, dst.tmode, dst.cross_mode, dst.dtcs_polarity, dst.skip,
                   dst.comment)),
    }
    for kind, (before, after) in pairs.items():
        if before != after:
            found.append((kind, str(before), str(after)))
    return found


def compare_written(dst, final, expected_extras):
    problems = rules.programming_differences(mem_to_wire(dst), mem_to_wire(final))
    if dst.name.rstrip() != (final.name or "").rstrip():
        problems.append("name")
    if (dst.skip or "") != (final.skip or ""):
        problems.append("skip")
    if (dst.comment or "") != (final.comment or ""):
        problems.append("comment")
    if str(dst.power) != str(final.power):
        problems.append("power")
    actual_extras = extras_json(final)
    for name, value in expected_extras.items():
        if actual_extras.get(name) != value:
            problems.append(f"extra:{name}")
    return problems


def ordinary_states(radio, lo, hi):
    return {str(n): mem_state(read_memory(radio, n)) for n in range(lo, hi + 1)}


def special_states(radio, rf):
    return {s: mem_state(radio.get_memory(s)) for s in rf.valid_special_chans}


def state_differences(label, expected, actual):
    problems = []
    for key in sorted(set(expected) | set(actual), key=str):
        if expected.get(key) != actual.get(key):
            problems.append(f"{label} {key}: expected {expected.get(key)!r}, found {actual.get(key)!r}")
    return problems


def level_by_name(rf, levels, name):
    label = levels.get(name)
    if label is None:
        raise WorkerError(f"Profile has no radio level for power '{name}'",
                          [f"levels: {levels}", f"model offers {[str(p) for p in rf.valid_power_levels]}"])
    for level in rf.valid_power_levels:
        if str(level) == label:
            return level
    raise WorkerError(f"Power level {label!r} not offered by this model",
                      [str(p) for p in rf.valid_power_levels])


def resolve_power(rf, power_policy):
    """(forced level, level for channels without power); None where not applicable."""
    if not rf.valid_power_levels:
        return None, None
    levels = power_policy.get("levels", {})
    forced = None
    if power_policy.get("force"):
        forced = level_by_name(rf, levels, power_policy["force"])
    default = level_by_name(rf, levels, power_policy.get("default", "high"))
    return forced, default


def write_channel(radio, rf, number, src, profile, csv_features, power_levels):
    problems = []
    forced, default = power_levels
    try:
        dst = import_logic.import_mem(radio, csv_features, src)
        if (rf.valid_tuning_steps and not rf.has_nostep_tuning
                and dst.tuning_step not in rf.valid_tuning_steps):
            dst.tuning_step = chirp_common.required_step(dst.freq, rf.valid_tuning_steps)
        chosen = forced if forced is not None else default if src.power is None else None
        if chosen is not None:
            dst.power = chosen
    except (import_logic.ImportError, errors.RadioError, errors.InvalidDataError,
            chirp_common.ImmutableValueError, ValueError) as exc:
        return None, [], [], [str(exc)]
    adaptations = adaptation_kinds(src, dst, rf)
    if chosen is not None:
        adaptations = [a for a in adaptations if a[0] != "power"]
    allowed = set(profile["allowed_adaptations"])
    for kind, before, after in adaptations:
        if kind not in allowed:
            problems.append(f"adaptation '{kind}' not allowed by profile: {before} -> {after}")
    validation = [str(m) for m in radio.validate_memory(dst)]
    if validation and profile["validation_warnings"] == "error":
        problems.extend(f"CHIRP warning: {m}" for m in validation)
    if problems:
        return None, adaptations, validation, problems
    radio.set_memory(dst)
    current = radio.get_memory(number)
    names = {rs.get_name() for rs in (current.extra or [])}
    missing = sorted(names - set(profile["extras"]))
    if missing:
        return None, adaptations, validation, [f"profile has no value for extras: {', '.join(missing)}"]
    expected_extras = {}
    if current.extra:
        for rs in current.extra:
            apply_setting_json(rs, profile["extras"][rs.get_name()], f"extra {rs.get_name()}")
            expected_extras[rs.get_name()] = setting_json(rs)
        current.comment = dst.comment
        radio.set_memory(current)
    radio.set_memory_extra(dst)
    final = read_memory(radio, number)
    mismatched = compare_written(dst, final, expected_extras)
    if mismatched:
        return None, adaptations, validation, [f"driver stored different values for: {', '.join(mismatched)}"]
    return names, adaptations, validation, []


def op_build(req):
    template = Path(req["template"])
    staging = Path(req["output"])
    profile = req["profile"]
    if staging.exists():
        raise WorkerError(f"Output {staging} already exists")
    radio = load_image(template)
    if identity(radio) != req["identity"]:
        raise WorkerError("Template identity does not match profile",
                          [f"template {identity(radio)}", f"profile {req['identity']}"])
    sig_sha = signature_sha256(signature(radio))
    if sig_sha != req["signature_sha256"]:
        raise WorkerError("Model capabilities differ from the registered signature "
                          "(CHIRP driver changed?). Re-register the template.")
    rf = radio.get_features()
    lo, hi = rf.memory_bounds
    channels = req["channels"]
    if len(channels) > hi - lo + 1:
        raise WorkerError(f"{len(channels)} channels do not fit in {hi - lo + 1} memories")
    power_levels = resolve_power(rf, profile["power"])
    before_settings = settings_snapshot(radio)
    before_specials = special_states(radio, rf)
    csv_features = generic_csv.CSVRadio(None).get_features()

    problems = []
    adaptations = []
    validation = []
    assigned = []
    seen_extras = set()
    for index, channel in enumerate(channels):
        number = lo + index
        ref = channel["ref"]
        try:
            src = wire_to_mem(channel["wire"], number)
        except ValueError as exc:
            problems.append({"number": number, "ref": ref, "error": str(exc)})
            continue
        names, adapted, warned, errs = write_channel(
            radio, rf, number, src, profile, csv_features, power_levels)
        adaptations.extend({"number": number, "ref": ref, "kind": k, "before": b, "after": a}
                           for k, b, a in adapted)
        validation.extend({"number": number, "ref": ref, "warning": w} for w in warned)
        problems.extend({"number": number, "ref": ref, "error": e} for e in errs)
        if names is not None:
            seen_extras |= names
            assigned.append({"number": number, "ref": ref})
    unknown = sorted(set(profile["extras"]) - seen_extras) if seen_extras else []
    if unknown:
        problems.append({"number": None, "ref": None,
                         "error": f"profile extras not offered by this model: {', '.join(unknown)}"})
    if problems:
        raise WorkerError("Build rejected", problems)

    for number in range(lo + len(channels), hi + 1):
        if not radio.get_memory(number).empty:
            radio.erase_memory(number)
        radio.erase_memory_extra(number)
        if not read_memory(radio, number).empty:
            raise WorkerError(f"Memory {number} could not be erased")

    overrides = profile["settings"]
    applied, settings_changed = apply_setting_overrides(
        radio, overrides, set(profile["acknowledged_warnings"]))
    expected_settings = dict(before_settings)
    expected_settings.update(applied)
    after_settings = settings_snapshot(radio)
    checks = state_differences("setting", expected_settings, after_settings)
    after_specials = special_states(radio, rf)
    checks += state_differences("special memory", before_specials, after_specials)
    states = ordinary_states(radio, lo, hi)
    if checks:
        raise WorkerError("Unexpected changes after applying settings", checks)

    radio.save(str(staging))
    try:
        reloaded = load_image(staging)
        checks = []
        if identity(reloaded) != identity(radio):
            checks.append(f"identity after reload {identity(reloaded)}")
        checks += state_differences("memory", states, ordinary_states(reloaded, lo, hi))
        checks += state_differences("special memory", after_specials,
                                    special_states(reloaded, rf))
        checks += state_differences("setting", after_settings, settings_snapshot(reloaded))
        before_raw = stripped_bytes(radio, template)
        after_raw = stripped_bytes(reloaded, staging)
        if len(before_raw) != len(after_raw):
            checks.append(f"image size changed {len(before_raw)} -> {len(after_raw)}")
        if checks:
            raise WorkerError("Saved image does not reload identically", checks)
    except Exception:
        staging.unlink(missing_ok=True)
        raise

    changed = [i for i, (a, b) in enumerate(zip(before_raw, after_raw)) if a != b]
    return {
        "identity": identity(radio),
        "chirp_version": CHIRP_VERSION,
        "channels": assigned,
        "adaptations": adaptations,
        "validation_warnings": validation,
        "settings_changed": settings_changed,
        "settings_applied": applied,
        "expected": {"memories": states, "specials": after_specials, "settings": after_settings},
        "raw": {"size": len(after_raw), "changed_bytes": len(changed)},
    }


def op_verify(req):
    radio = load_image(req["path"])
    rf = radio.get_features()
    lo, hi = rf.memory_bounds
    expected = req["expected"]
    problems = []
    if identity(radio) != req["identity"]:
        problems.append(f"identity {identity(radio)} does not match {req['identity']}")
    else:
        problems += state_differences("memory", expected["memories"], ordinary_states(radio, lo, hi))
        problems += state_differences("special memory", expected["specials"], special_states(radio, rf))
        problems += state_differences("setting", expected["settings"], settings_snapshot(radio))
    return {"identity": identity(radio), "chirp_version": CHIRP_VERSION, "problems": problems}


def op_settings_diff(req):
    base = load_image(req["template"])
    other = load_image(req["image"])
    if identity(base) != identity(other):
        raise WorkerError("Images are different models",
                          [f"template {identity(base)}", f"image {identity(other)}"])
    described = {d["path"]: d for d in describe_settings(other)}
    a = settings_snapshot(base)
    b = settings_snapshot(other)
    diffs = []
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            info = described.get(key, {})
            diffs.append({"path": key, "template": a.get(key), "image": b.get(key),
                          "mutable": info.get("mutable", False),
                          "overridable": info.get("overridable", False)})
    return {"differences": diffs}


def op_version(_req):
    return {"chirp_version": CHIRP_VERSION}


OPERATIONS = {
    "version": op_version,
    "inspect": op_inspect,
    "read_channels": op_read_channels,
    "normalize": op_normalize,
    "write_csv": op_write_csv,
    "build": op_build,
    "verify": op_verify,
    "settings_diff": op_settings_diff,
}


def main():
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    collector = LogCollector()
    logging.getLogger().addHandler(collector)
    logging.getLogger().setLevel(logging.WARNING)
    try:
        request = json.loads(sys.stdin.read())
        result = OPERATIONS[request["op"]](request)
        response = {"ok": True, "result": result}
    except WorkerError as exc:
        response = {"ok": False, "error": str(exc), "details": exc.details}
    except Exception as exc:
        response = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "details": traceback.format_exc().splitlines()[-15:]}
    response["log"] = collector.records[-200:]
    response["chirp_version"] = CHIRP_VERSION
    real_stdout.write(json.dumps(response))
    real_stdout.flush()
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
