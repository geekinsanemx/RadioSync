# radiosync

Master memory catalog for CHIRP-programmable radios. It stores each programming only once
(SQLite), groups programmings into combinable *sets* and generates, per radio **model**, a
validated `.img` image with its settings, ready to load from CHIRP.

Version: 0.1.11

## What it solves

- One master list for all your radios; each model gets its own image.
- Reusable sets (`personal`, `repeaters`, `scanner`, ...) combined at build time.
- Import from CHIRP CSV files, `.img` images and JSON catalogs, without duplicating channels.
- Per-model settings stored as JSON and applied on top of an image downloaded from the radio.
- Validation before loading: the image is reopened with CHIRP and compared with the expected state.

## Quick install

Requirements: Python 3.11+, [pipx](https://pipx.pypa.io/) and CHIRP installed in its own
environment (for example `pipx install chirp`).

```bash
pipx install .
radiosync init
radiosync where
```

## Quick start

```bash
radiosync radios register --template /path/to/download.img
radiosync channels import /path/to/channels.csv --set personal
radiosync build --dry-run -v
radiosync build
radiosync validate
```

The `.img` and `.manifest.json` files are written to the current directory (or to
`--output`). Internal data (catalog, profiles, templates and backups) lives in
`~/.config/radiosync/`.

## Documentation

| Document | Contents |
|---|---|
| [docs/usage-guide.md](docs/usage-guide.md) | Full workflow: models, import, sets, builds, power, ordering, names, validation, settings and backups |
| [docs/cli-reference.md](docs/cli-reference.md) | Every command, option and environment variable |
| [docs/architecture.md](docs/architecture.md) | Storage, CHIRP process, image build and verification, deduplication |
| [docs/formats.md](docs/formats.md) | Radio profile, preset, JSON catalog and manifest |
| [CHANGELOG.md](CHANGELOG.md) | Changes per version |

## Limits

Validation confirms what the CHIRP driver can read and write; it does not test firmware
compatibility, RF behavior or authorization to transmit. Use as the template an image
downloaded from the same model, and review the image in CHIRP before loading it.

## Development

```bash
uv sync
uv run pytest
RADIOSYNC_TEST_TEMPLATE=/path/to/download.img uv run pytest tests/test_chirp_integration.py
pipx install --force .
```

`pipx install .` copies the code; after modifying it, reinstall with `--force`.
