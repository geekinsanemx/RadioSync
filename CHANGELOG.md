# Changelog

## 0.1.11 - 2026-11-02

- Documentation in English: README and `docs/` (`usage-guide.md`, `cli-reference.md`,
  `architecture.md`, `formats.md`, replacing the Spanish file names).
- Name fitting drops English stopwords (`of`, `the`, `and`) as well as the Spanish ones,
  so `Hill of Peace` -> `HillPc`; tests cover both languages.

## 0.1.10 - 2026-11-02

- Neutral place-name examples in the name-fitting tests.
- `.gitignore` merges GitHub's Python template with the project rules.

## 0.1.9 - 2026-11-01

- Documentation: README overview plus `docs/` (usage guide, CLI reference, architecture, formats).
- Generic example names in tests and docs; no catalog data in the repository.
- Stricter `.gitignore` for databases, backups, manifests, signatures, catalog exports and `config/`.
- `alembic.ini` no longer points to a repository database; manual Alembic uses the active storage.
- Help text for `where` and `validate` matches storage and output locations.

## 0.1.8 - 2026-11-01

- `--sort` orders generated images and CHIRP CSV exports by RX frequency.
- Sorting is stable after deduplication and does not modify set order; manifests record the ordering mode.

## 0.1.7 - 2026-11-01

- Generated image and CSV comments start with all catalog set memberships, followed by the original comment.
- Catalog comments remain unchanged by generation; repeated exports do not accumulate annotations.

## 0.1.6 - 2026-11-01

- Build filenames use model, YYYYMMDD and the first eight characters of the image SHA-256.
- Identical images and build details reuse existing outputs without rewriting them.
- Conflicting output names receive numeric suffixes; existing files are never overwritten.

## 0.1.5 - 2026-11-01

- Internal configuration, catalog, templates and backups live in the user configuration directory.
- Builds write flat image/manifest pairs in cwd or --output; validate reads that location.
- CSV/JSON exports can omit --output to use an automatic filename in cwd.
- Original project data and prior outputs are retained during migration.

## 0.1.4 - 2026-11-01

- Name fitting (`radiosync.names`): names longer than a model allows are shortened at
  build time and in `channels export --radio` (`REP-ABC-123` -> `ABC123`), with collision
  numbering; reported as `name_fit`. Profile option `name_fit` (default on).

## 0.1.3 - 2026-11-01

- Channels imported from CHIRP CSV or images no longer keep a power value; the radio
  profile (`power.default`, or `--power`) decides it at build time.

## 0.1.2 - 2026-11-01

- `--power low|mid|high` on `build` and on `channels export --format chirp-csv --radio`.
- Profiles map low/mid/high to each model's levels and define the level for channels
  without power (`power.levels`, `power.default`); `register` fills them from the driver.
- Output file names include the forced power level.

## 0.1.1 - 2026-11-01

- Install with `pipx install .` and run `radiosync` from any directory.
- Project lookup: `--home`, `RADIOSYNC_HOME`, current directory upwards, then the
  default project in `~/.config/radiosync/config.toml` recorded by `init`.
- `init --set-default` changes the default project; new `radiosync where` command.

## 0.1.0 - 2026-11-01

- SQLite catalog (SQLAlchemy + Alembic) with deduplication by RF programming.
- Ordered, combinable channel sets with per-set alias/skip; `personal` first by default.
- Import from CHIRP CSV, CHIRP images and JSON catalogs; export to CHIRP CSV and JSON.
- Manual memory entry and editing, with options or interactive prompts.
- Per-model profiles with registered template, capability signature, power policy,
  allowed adaptations, per-channel extras and typed settings overrides.
- Image build through CHIRP drivers in a separate process, with readback, reload and
  settings/special-memory checks; batch published only when every model passes.
- `validate` re-checks published images against their manifests.
- Settings export, diff and import from an image.
- Timestamped backups of the database, profiles, presets and overwritten files.
