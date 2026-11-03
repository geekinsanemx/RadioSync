"""radiosync memory_rules: canonical form and identity of a channel programming.

Pure standard library so both the application and the CHIRP worker load it.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

import hashlib
import json

WIRE_FIELDS = (
    "freq_hz", "duplex", "offset_hz", "mode", "tmode", "rtone_dhz",
    "ctone_dhz", "dtcs", "rx_dtcs", "dtcs_polarity", "cross_mode", "name",
    "comment", "skip", "power_mw", "tuning_step_hz",
)

TONE_DEFAULTS = {
    "rtone_dhz": 885,
    "ctone_dhz": 885,
    "dtcs": 23,
    "rx_dtcs": 23,
    "dtcs_polarity": "NN",
    "cross_mode": "Tone->Tone",
}

IDENTITY_FIELDS = (
    "freq_hz", "duplex", "offset_hz", "mode", "tmode", "rtone_dhz",
    "ctone_dhz", "dtcs", "rx_dtcs", "dtcs_polarity", "cross_mode",
)

DUPLEX_VALUES = ("", "+", "-", "split", "off")
SKIP_VALUES = ("", "S", "P")


def active_tone_fields(tmode: str, cross_mode: str) -> frozenset[str]:
    """Tone fields that affect RF behavior for a tone mode."""
    if tmode == "":
        return frozenset()
    if tmode == "Tone":
        return frozenset({"rtone_dhz"})
    if tmode in ("TSQL", "TSQL-R"):
        return frozenset({"ctone_dhz"})
    if tmode in ("DTCS", "DTCS-R"):
        return frozenset({"dtcs", "dtcs_polarity"})
    if tmode == "Cross":
        tx, _, rx = cross_mode.partition("->")
        fields = {"cross_mode"}
        if tx == "Tone":
            fields.add("rtone_dhz")
        if tx == "DTCS":
            fields.add("dtcs")
        if rx == "Tone":
            fields.add("ctone_dhz")
        if rx == "DTCS":
            fields.add("rx_dtcs")
        if "DTCS" in (tx, rx):
            fields.add("dtcs_polarity")
        return frozenset(fields)
    raise ValueError(f"Unknown tone mode {tmode!r}")


def canonical(wire: dict) -> dict:
    """Return @wire with inactive fields reset so equal programmings compare equal."""
    missing = [f for f in WIRE_FIELDS if f not in wire]
    if missing:
        raise ValueError(f"Missing memory fields: {', '.join(missing)}")
    result = {f: wire[f] for f in WIRE_FIELDS}
    active = active_tone_fields(result["tmode"], result["cross_mode"])
    for field, default in TONE_DEFAULTS.items():
        if field not in active:
            result[field] = default
    if result["duplex"] in ("", "off"):
        result["offset_hz"] = 0
    result["name"] = (result["name"] or "").rstrip()
    result["comment"] = (result["comment"] or "").strip()
    result["skip"] = result["skip"] or ""
    return result


def identity(wire: dict) -> dict:
    """Fields that define the RF programming, excluding presentation."""
    canon = canonical(wire)
    return {f: canon[f] for f in IDENTITY_FIELDS}


def fingerprint(wire: dict) -> str:
    """Stable SHA-256 of the RF programming of @wire."""
    payload = json.dumps(identity(wire), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def programming_differences(expected: dict, actual: dict,
                            fields: tuple[str, ...] = IDENTITY_FIELDS) -> list[str]:
    """Names of @fields whose canonical values differ."""
    a = canonical(expected)
    b = canonical(actual)
    return [f for f in fields if a[f] != b[f]]
