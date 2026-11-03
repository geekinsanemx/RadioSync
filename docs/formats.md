# Formats

Every file is JSON except `config.toml`. The examples use fictitious values.

## Radio profile

`radios/<id>.json` in the storage. Created by `radios register`; you can edit the
configuration fields.

```json
{
  "schema_version": 1,
  "id": "vendor-model",
  "identity": {"vendor": "Vendor", "model": "Model", "variant": "", "rclass": "DriverClass"},
  "template": {
    "file": "templates/vendor-model.img",
    "sha256": "<sha256>",
    "signature_sha256": "<sha256>",
    "chirp_version": "<version>",
    "registered_at": "<iso-8601>"
  },
  "enabled": true,
  "default_sets": ["personal", "repeaters"],
  "power": {"levels": {"low": "Low", "mid": "Mid", "high": "High"}, "default": "high"},
  "allowed_adaptations": ["power", "tuning_step", "name_case", "tone", "dtcs", "duplex"],
  "validation_warnings": "error",
  "name_fit": true,
  "extras": {"bcl": false},
  "settings": {"basic/settings.squelch": "3"},
  "acknowledged_warnings": []
}
```

| Field | Use |
|---|---|
| `identity`, `template` | Written by `register`; do not edit them |
| `enabled` | Include the model in `build` without `--radio` |
| `default_sets` | Sets used when neither `--sets` nor `--preset` is given |
| `power.levels` | Radio level for `low`, `mid`, `high` |
| `power.default` | Level for channels without power |
| `allowed_adaptations` | Changes accepted when adapting a channel: `power`, `tuning_step`, `name_case`, `name_length`, `name_chars`, `name_other`, `tone`, `dtcs`, `mode`, `duplex` |
| `validation_warnings` | `error` or `report` for CHIRP warnings |
| `name_fit` | Shorten names to the model (`true` by default) |
| `extras` | Value of each per-channel driver option; required for every option the driver offers |
| `settings` | Settings to force, strictly typed; paths come from `settings export` |
| `acknowledged_warnings` | Setting paths whose driver warning you accept |

## Preset

`presets/<name>.json`:

```json
{"description": "Daily use", "sets": ["personal", "repeaters"], "radios": null}
```

`radios: null` applies to every enabled model.

## JSON catalog

Produced by `db export` and `channels export --format json`; read by `db import` and
`channels import`.

```json
{
  "format": "radiosync-catalog",
  "version": 1,
  "memories": [
    {
      "freq_hz": 146520000, "duplex": "", "offset_hz": 0, "mode": "FM",
      "tmode": "", "rtone_dhz": 885, "ctone_dhz": 885, "dtcs": 23, "rx_dtcs": 23,
      "dtcs_polarity": "NN", "cross_mode": "Tone->Tone",
      "name": "CALL", "comment": "", "skip": "", "power_mw": null, "tuning_step_hz": null,
      "fingerprint": "<sha256>"
    }
  ],
  "sets": [
    {"name": "personal", "description": "", "members": [
      {"fingerprint": "<sha256>", "alias": null, "skip": null}
    ]}
  ]
}
```

| Field | Unit / values |
|---|---|
| `freq_hz`, `offset_hz` | Hz. With `duplex: "split"`, `offset_hz` is the TX frequency |
| `duplex` | `""`, `"+"`, `"-"`, `"split"`, `"off"` |
| `rtone_dhz`, `ctone_dhz` | Tenths of Hz (885 = 88.5 Hz) |
| `power_mw` | mW, or `null` for the radio's power |
| `tuning_step_hz` | Hz, or `null` for automatic |

On import, the fingerprint is recalculated; existing memories are reused and each set's
members are added if missing.

## Manifest

`<radio-id>_<YYYYMMDD>_<hash8>.manifest.json`, next to its `.img`. It is not loaded into
the radio: `validate` uses it to verify the image.

| Field | Content |
|---|---|
| `format`, `version` | `radiosync-manifest`, `1` |
| `radio`, `identity` | Model and its CHIRP identity |
| `created_at`, `radiosync_version`, `chirp_version` | Date and versions |
| `template_sha256`, `signature_sha256` | Template and signature used |
| `sets`, `power`, `sort` | Build selection (`sort`: `sets` or `frequency`) |
| `image` | `file`, full `sha256` and `size` |
| `channels` | Position, memory, fingerprint, name and source sets |
| `adaptations` | Changes made when adapting each channel (`name_fit`, `power`, ...) |
| `validation_warnings` | CHIRP warnings |
| `settings_applied` | Forced settings and their final value |
| `raw` | Size and bytes that changed relative to the template |
| `expected` | Expected state of memories, special memories and settings |
