# CLI reference

`radiosync --help` and `radiosync <command> --help` show the same information.

## Global option

| Option | Use |
|---|---|
| `--home <path>` | Alternative internal storage; takes precedence over `RADIOSYNC_HOME` and `XDG_CONFIG_HOME` |

## Environment variables

| Variable | Use |
|---|---|
| `RADIOSYNC_HOME` | Alternative internal storage |
| `XDG_CONFIG_HOME` | Base of the default storage (`$XDG_CONFIG_HOME/radiosync`) |
| `RADIOSYNC_CHIRP_PYTHON` | Python interpreter of the CHIRP environment |
| `PIPX_HOME` | Base used to find the CHIRP pipx environment |
| `RADIOSYNC_TEST_TEMPLATE` | Tests only: image for the integration tests |

## General

| Command | Description |
|---|---|
| `init` | Creates the storage, the database and the `personal` set; shows the CHIRP version |
| `where` | Shows the storage, database, output directory and CHIRP interpreter |
| `version` | radiosync and CHIRP versions |

## build

```text
radiosync build [--radio <id>]... [--sets a,b | --preset <name>] [--output <dir>]
                [--power low|mid|high] [--sort] [--dry-run] [-v]
```

| Option | Use |
|---|---|
| `--radio <id>` | Model; repeatable. Without it: every enabled model (or the preset's) |
| `--sets a,b` | Sets to combine. Without it: each profile's `default_sets` |
| `--preset <name>` | Saved combination; mutually exclusive with `--sets` |
| `--output`, `-o <dir>` | Output directory; the current one by default |
| `--power low\|mid\|high` | Every channel at the profile level with that name |
| `--sort` | Order by RX frequency instead of by sets |
| `--dry-run` | Build and verify without publishing |
| `--verbose`, `-v` | List every adaptation |

## validate

```text
radiosync validate [--radio <id>]... [--output <dir>] [--manifest <file>]...
```

| Option | Use |
|---|---|
| `--radio <id>` | Only these models; repeatable |
| `--output`, `-o <dir>` | Directory to search for manifests; the current one by default |
| `--manifest <file>` | Specific manifests; repeatable |

Without `--manifest`, it validates the latest manifest of each model in the directory.

## channels

| Command | Options | Description |
|---|---|---|
| `import <file>` | `--set <name>`, `--dry-run` | Imports `.csv`, `.img` or a `.json` catalog |
| `export` | `--sets a,b`, `--format chirp-csv\|json`, `--output <file>`, `--radio <id>`, `--power`, `--sort` | Exports a CSV composition or a JSON catalog |
| `list` | `--set <name>`, `--search <text>` | Lists memories or the members of a set |
| `show <id>` | | Details and sets of a memory |
| `add` | memory fields, `--set <name>` (repeatable), `-i` | Creates a memory |
| `edit <id>` | memory fields, `-i` | Modifies a memory |
| `delete <id>` | `--force` | Deletes a memory (`--force` removes it from its sets) |

`export` rules:

- `chirp-csv` (the default) requires `--sets`; `json` without `--sets` exports the whole
  catalog.
- `--radio` fits names to the model; `--power` requires `--radio`.
- `--radio`, `--power` and `--sort` apply only to `chirp-csv`.
- Without `--output`: `<sets|catalog>__<date>.csv|json` in the current directory.

Memory fields (`add` / `edit`):

| Option | Value |
|---|---|
| `--freq` | RX in MHz |
| `--name` | Name |
| `--duplex` | `simplex`, `+`, `-`, `split`, `off` |
| `--offset` | Offset in MHz (`+`/`-`) |
| `--tx-freq` | TX in MHz (`split`) |
| `--mode` | `FM`, `NFM`, `AM`, ... |
| `--tmode` | `none`, `Tone`, `TSQL`, `DTCS`, `Cross`, `TSQL-R`, `DTCS-R` |
| `--rtone` / `--ctone` | CTCSS in Hz (Tone / TSQL) |
| `--dtcs` / `--rx-dtcs` / `--polarity` | DCS code, RX DCS, `NN`/`NR`/`RN`/`RR` |
| `--cross-mode` | For example `Tone->DTCS` |
| `--power` | Watts; empty for the radio's power |
| `--step` | Step in kHz; empty for automatic |
| `--skip` | empty, `S` or `P` |
| `--comment` | Comment |

## sets

| Command | Options | Description |
|---|---|---|
| `create <name>` | `--description` | Creates an empty set |
| `list` | | Sets and their number of memories |
| `show <name>` | | Members in order |
| `add <name> <id>...` | `--position`, `--alias`, `--skip` | Adds memories |
| `remove <name> <id>...` | | Removes memories (they stay in the catalog) |
| `move <name> <id> <pos>` | | Changes the position |
| `member <name> <id>` | `--alias`, `--clear-alias`, `--skip`, `--clear-skip` | Alias/skip inside the set |
| `delete <name>` | `--yes` | Deletes the set (not the memories) |

## radios

| Command | Options | Description |
|---|---|---|
| `list` | | Models, memories, default sets, power levels |
| `register` | `--template <img>`, `--radio <id>`, `--replace` | Registers or replaces the template |
| `inspect` | `--radio <id>` | Capabilities and driver signature status |

## settings

| Command | Options | Description |
|---|---|---|
| `export` | `--radio <id>`, `--output <file>` | Every template setting as JSON (to the terminal without `--output`) |
| `diff` | `--radio <id>`, `--from <img>` | Differences between an image and the template |
| `import` | `--radio <id>`, `--from <img>`, `--dry-run` | Copies those differences into the profile |

## presets

| Command | Options | Description |
|---|---|---|
| `list` | | Saved presets |
| `create <name>` | `--sets a,b`, `--radios a,b`, `--description`, `--replace` | Saves a combination |

## db

| Command | Options | Description |
|---|---|---|
| `backup` | | Consistent copy of the database in `bkp/` |
| `export` | `--output <file>` | Whole catalog as JSON |
| `import <file>` | `--dry-run` | Merges a JSON catalog into the database |
