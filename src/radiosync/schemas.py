"""radiosync schemas: Pydantic models for memories, profiles, presets and exchange files.

Changelog:
- 0.1.8 (2026-11-01): manifest records channel sort.
- 0.1.4 (2026-11-01): RadioProfile.name_fit.
- 0.1.2 (2026-11-01): PowerPolicy maps low/mid/high to radio levels with a default.
- 0.1.0 (2026-11-01): initial version.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

RADIO_ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"
SET_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"

AdaptationKind = Literal[
    "power", "tuning_step", "name_case", "name_length", "name_chars", "name_other",
    "tone", "dtcs", "mode", "duplex",
]
DEFAULT_ADAPTATIONS: list[AdaptationKind] = ["power", "tuning_step", "name_case", "tone",
                                             "dtcs", "duplex"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemoryInput(Strict):
    """One channel programming in wire units (Hz, tenths of Hz, mW)."""

    freq_hz: int = Field(gt=0)
    duplex: Literal["", "+", "-", "split", "off"] = ""
    offset_hz: int = Field(default=0, ge=0)
    mode: str = "FM"
    tmode: str = ""
    rtone_dhz: int = 885
    ctone_dhz: int = 885
    dtcs: int = 23
    rx_dtcs: int = 23
    dtcs_polarity: str = "NN"
    cross_mode: str = "Tone->Tone"
    name: str = ""
    comment: str = ""
    skip: Literal["", "S", "P"] = ""
    power_mw: int | None = Field(default=None, gt=0)
    tuning_step_hz: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _split_needs_tx(self):
        if self.duplex == "split" and self.offset_hz <= 0:
            raise ValueError("split duplex needs the TX frequency in offset_hz")
        return self


class Identity(Strict):
    vendor: str
    model: str
    variant: str = ""
    rclass: str


class TemplateInfo(Strict):
    file: str
    sha256: str
    signature_sha256: str
    chirp_version: str
    registered_at: str


PowerName = Literal["low", "mid", "high"]
POWER_NAMES: tuple[str, ...] = ("low", "mid", "high")


class PowerPolicy(Strict):
    """Radio level label for each generic power name, and the one used when a channel has none."""

    levels: dict[PowerName, str] = Field(default_factory=dict)
    default: PowerName = "high"


class RadioProfile(Strict):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=RADIO_ID_PATTERN)
    identity: Identity
    template: TemplateInfo
    enabled: bool = True
    default_sets: list[str] = Field(default_factory=lambda: ["personal"], min_length=1)
    power: PowerPolicy = Field(default_factory=PowerPolicy)
    allowed_adaptations: list[AdaptationKind] = Field(
        default_factory=lambda: list(DEFAULT_ADAPTATIONS))
    validation_warnings: Literal["error", "report"] = "error"
    name_fit: bool = True
    extras: dict[str, JsonValue] = Field(default_factory=dict)
    settings: dict[str, JsonValue] = Field(default_factory=dict)
    acknowledged_warnings: list[str] = Field(default_factory=list)

    def worker_policy(self, force_power: str | None = None) -> dict:
        return {
            "extras": self.extras,
            "settings": self.settings,
            "acknowledged_warnings": self.acknowledged_warnings,
            "power": dict(self.power.model_dump(), force=force_power),
            "allowed_adaptations": self.allowed_adaptations,
            "validation_warnings": self.validation_warnings,
        }


class Preset(Strict):
    description: str = ""
    sets: list[str] = Field(min_length=1)
    radios: list[str] | None = None


class CatalogMemory(MemoryInput):
    fingerprint: str | None = None


class CatalogMember(Strict):
    fingerprint: str
    alias: str | None = None
    skip: Literal["", "S", "P"] | None = None


class CatalogSet(Strict):
    name: str = Field(pattern=SET_NAME_PATTERN)
    description: str = ""
    members: list[CatalogMember] = Field(default_factory=list)


class Catalog(Strict):
    format: Literal["radiosync-catalog"] = "radiosync-catalog"
    version: Literal[1] = 1
    memories: list[CatalogMemory] = Field(default_factory=list)
    sets: list[CatalogSet] = Field(default_factory=list)


class ManifestImage(Strict):
    file: str
    sha256: str
    size: int


class Manifest(BaseModel):
    format: Literal["radiosync-manifest"]
    version: Literal[1]
    radio: str
    created_at: str
    radiosync_version: str
    chirp_version: str
    identity: Identity
    template_sha256: str
    signature_sha256: str
    sets: list[str]
    power: str | None = None
    sort: Literal["sets", "frequency"] = "sets"
    image: ManifestImage
    channels: list[dict]
    adaptations: list[dict]
    validation_warnings: list[dict]
    settings_applied: dict
    raw: dict
    expected: dict
