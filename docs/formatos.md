# Formatos

Todos los archivos son JSON salvo `config.toml`. Los ejemplos usan valores ficticios.

## Perfil de radio

`radios/<id>.json` en el almacenamiento. Lo crea `radios register`; puedes editar los
campos de configuración.

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
  "default_sets": ["personal", "repetidoras"],
  "power": {"levels": {"low": "Low", "mid": "Mid", "high": "High"}, "default": "high"},
  "allowed_adaptations": ["power", "tuning_step", "name_case", "tone", "dtcs", "duplex"],
  "validation_warnings": "error",
  "name_fit": true,
  "extras": {"bcl": false},
  "settings": {"basic/settings.squelch": "3"},
  "acknowledged_warnings": []
}
```

| Campo | Uso |
|---|---|
| `identity`, `template` | Los escribe `register`; no los edites |
| `enabled` | Incluir el modelo en `build` sin `--radio` |
| `default_sets` | Sets cuando no se indica `--sets`/`--preset` |
| `power.levels` | Nivel del radio para `low`, `mid`, `high` |
| `power.default` | Nivel para canales sin potencia |
| `allowed_adaptations` | Cambios aceptados al adaptar un canal: `power`, `tuning_step`, `name_case`, `name_length`, `name_chars`, `name_other`, `tone`, `dtcs`, `mode`, `duplex` |
| `validation_warnings` | `error` o `report` para las advertencias de CHIRP |
| `name_fit` | Acortar nombres al modelo (por defecto `true`) |
| `extras` | Valor de cada opción por canal del driver; obligatorio para todas las que ofrezca |
| `settings` | Settings a forzar con tipos estrictos; rutas en `settings export` |
| `acknowledged_warnings` | Rutas de settings cuyo aviso del driver aceptas |

## Preset

`presets/<name>.json`:

```json
{"description": "Uso diario", "sets": ["personal", "repetidoras"], "radios": null}
```

`radios: null` aplica a todos los modelos habilitados.

## Catálogo JSON

Lo producen `db export` y `channels export --format json`; lo leen `db import` y
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

| Campo | Unidad / valores |
|---|---|
| `freq_hz`, `offset_hz` | Hz. Con `duplex: "split"`, `offset_hz` es la TX |
| `duplex` | `""`, `"+"`, `"-"`, `"split"`, `"off"` |
| `rtone_dhz`, `ctone_dhz` | Décimas de Hz (885 = 88.5 Hz) |
| `power_mw` | mW, o `null` para la potencia del radio |
| `tuning_step_hz` | Hz, o `null` para automático |

Al importar, el fingerprint se recalcula; las memorias existentes se reutilizan y los
miembros de cada set se agregan si faltan.

## Manifiesto

`<radio-id>_<YYYYMMDD>_<hash8>.manifest.json`, junto a su `.img`. No se carga al radio:
`validate` lo usa para verificar la imagen.

| Campo | Contenido |
|---|---|
| `format`, `version` | `radiosync-manifest`, `1` |
| `radio`, `identity` | Modelo y su identidad en CHIRP |
| `created_at`, `radiosync_version`, `chirp_version` | Fecha y versiones |
| `template_sha256`, `signature_sha256` | Template y firma usados |
| `sets`, `power`, `sort` | Selección del build (`sort`: `sets` o `frequency`) |
| `image` | `file`, `sha256` completo y `size` |
| `channels` | Posición, memoria, fingerprint, nombre y sets de origen |
| `adaptations` | Cambios al adaptar cada canal (`name_fit`, `power`, ...) |
| `validation_warnings` | Advertencias de CHIRP |
| `settings_applied` | Settings forzados y su valor final |
| `raw` | Tamaño y bytes que cambiaron respecto al template |
| `expected` | Estado esperado de memorias, memorias especiales y settings |
