# Architecture

## Components

| Module | Responsibility |
|---|---|
| `cli.py` | Commands (Typer) |
| `config.py` | Storage, CHIRP interpreter, backups |
| `database.py`, `models.py`, `migrations/` | SQLite with SQLAlchemy and Alembic |
| `memory_rules.py` | Canonical form and identity of a programming |
| `catalog.py`, `sets.py` | Memories, import with deduplication, sets |
| `composition.py` | Set combination, comments and ordering |
| `names.py` | Fitting names to the model |
| `radios.py`, `settings.py` | Profiles, templates, settings |
| `build.py`, `validation.py` | Generation, publishing and verification |
| `csv_io.py`, `json_io.py` | CSV/image exchange and JSON catalog |
| `chirp_client.py`, `chirp_worker.py` | Bridge to CHIRP in a separate process |

## Storage

Internal data lives outside the code:

```text
~/.config/radiosync/            ($XDG_CONFIG_HOME/radiosync, RADIOSYNC_HOME or --home)
├── config.toml                 internal paths and [chirp] python
├── radios/<id>.json            per-model profile
├── presets/<name>.json         saved combinations
├── data/radiosync.db           catalog and sets
├── templates/<id>.img          registered base image
├── templates/<id>.signature.json  driver capabilities at registration
└── bkp/                        backups
```

Storage selection order: `--home`, `RADIOSYNC_HOME`, then `$XDG_CONFIG_HOME/radiosync` or
`~/.config/radiosync`. The current directory never selects another catalog; it is only the
default destination for builds and exports.

`config.toml`:

```toml
[paths]
database = "data/radiosync.db"
templates = "templates"
backups = "bkp"
radios = "radios"
presets = "presets"

[chirp]
python = "/path/to/chirp/venv/bin/python"   # optional
```

CHIRP interpreter, in this order: `RADIOSYNC_CHIRP_PYTHON`, `[chirp] python` in
`config.toml`, and the CHIRP pipx environment (`$PIPX_HOME/venvs/chirp`,
`~/.local/share/pipx/venvs/chirp`, `~/.local/pipx/venvs/chirp`).

## Backups

| What | When | How |
|---|---|---|
| Database | Before every command that writes and before a schema migration | SQLite backup API |
| Radio profile | Before overwriting it | Copy |
| Template and signature | `radios register --replace` | Copy |
| Preset / exported file | Before overwriting it | Copy |

Format: `bkp/<file>.bkp-<YYMMDDHHmmss>` (with `-1`, `-2`, ... if the second collides).

## CHIRP bridge

radiosync does not import CHIRP. `chirp_client.py` runs `chirp_worker.py` with the CHIRP
interpreter (`python -I -B`), sends it a JSON request on stdin and reads a JSON response
on stdout. The worker does not open serial ports: it only reads images/CSV files and
writes new files.

| Operation | Use |
|---|---|
| `version` | CHIRP version |
| `inspect` | Identity, capabilities, signature, extras and settings of an image |
| `read_channels` | Memories from a CSV file or image |
| `normalize` | Validates and normalizes memories with the CHIRP rules |
| `write_csv` | Writes a CSV with the CHIRP generic driver |
| `build` | Generates and verifies an image |
| `verify` | Compares an image with the expected state |
| `settings_diff` | Settings differences between two images |

The worker runs `gettext.install("CHIRP")` before loading the drivers: some drivers use
`_()`, which only the CHIRP GUI defines.

## Memory identity

`memory_rules.py` defines the canonical form and the fingerprint (SHA-256):

- Part of the identity: RX frequency, duplex, offset/TX, mode, tone mode and the tones/DTCS
  that are **active** for that mode, polarity and cross mode when they apply.
- Not part of the identity: name, comment, power, skip and step.
- Inactive tones are normalized, so two identical RF programmings compare equal.
- The fingerprint is unique in the database: importing an existing programming reuses it.

Internal units: Hz (frequencies and offsets), tenths of Hz (CTCSS), mW (power).

## Building an image

For each model, in a temporary directory:

1. Verifies the template SHA-256 and that the driver capability signature did not change.
2. Composes the sets: deduplicates, applies alias/skip, `Sets: ...` comments and `--sort`.
3. Fits the names to the model (`names.py`).
4. For each channel, CHIRP's `import_logic.import_mem` adapts it to the model; the step is
   adjusted if needed and the before/after state is compared against
   `allowed_adaptations`; the driver's `validate_memory` runs.
5. Applies power (forced, from the channel, or `power.default`) and the profile `extras`.
6. Writes the memory, reads it back and compares what was stored.
7. Deletes leftover ordinary memories; special memories (VFO) are not touched.
8. Applies settings only if one of them changes, just like the CHIRP GUI.
9. Verifies that no other setting or special memory changed.
10. Saves the image, reloads it and compares memories, special memories and settings again.

If every model passes, the `.img` and manifest are published to the destination; if one
fails, none is published. `validate` repeats the step 10 comparison against the manifest.

Validation confirms what the driver can read and write; it does not test firmware, RF
behavior or authorization to transmit.

## Migrations

The schema is versioned with Alembic (`src/radiosync/migrations/`). The application
applies pending migrations when it opens the database, after backing it up. For manual use
from the repository, `alembic` uses the database of the active storage:

```bash
uv run alembic current
```
