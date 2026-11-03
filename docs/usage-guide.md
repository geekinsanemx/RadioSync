# Usage guide

The full radiosync workflow, from registering a model to loading the image into the radio.
Paths and names are examples: replace them with your own.

## 1. Initialize

```bash
radiosync init
radiosync where
```

`init` creates the internal storage (see [architecture](architecture.md#storage)), the
database and the `personal` set, and checks that it can find the CHIRP interpreter.
`where` shows the storage, the database, the current output directory and the CHIRP
interpreter in use.

## 2. Register models

Download the radio image with CHIRP (*Radio → Download*), save it and register it:

```bash
radiosync radios register --template /path/to/download.img
radiosync radios list
radiosync radios inspect --radio <radio-id>
```

- The id is derived from vendor and model (`baofeng-uv-5r-mini`); `--radio <id>` sets it.
- The image is copied as the template, together with its SHA-256 and a driver capability
  signature.
- Every radio of the same model receives the same image; there are no per-unit profiles.
- `register` fills in the driver's per-channel values (`extras`) and power levels.
- `--replace` changes the template of an already registered model and backs up the old one.
- `inspect` warns when a CHIRP update changed the driver capabilities; in that case,
  register again with `--replace`.

## 3. Import memories

```bash
radiosync channels import /path/to/channels.csv --set personal --dry-run
radiosync channels import /path/to/channels.csv --set personal
radiosync channels import /path/to/radio.img --set scanner
radiosync channels import /path/to/catalog.json
```

- CSV files and images are read with the CHIRP drivers.
- An identical programming (same RX, duplex/offset or TX, mode and active tones) is
  reused, not duplicated. If the name or comment differ, the existing one is kept and the
  difference is reported.
- The same frequency with a different tone, offset or mode is a separate memory.
- The whole file is rejected if it has unknown columns, repeated `Location` values, rows
  without a frequency, or D-STAR memories.
- Power from CSV files and images is not imported: each radio decides it (see
  [power](#7-power)).
- `--dry-run` shows the result without saving.

## 4. Create and edit memories

```bash
radiosync channels add --freq 146.520 --name CALL --set personal
radiosync channels add --freq 147.000 --duplex + --offset 0.6 --tmode TSQL --ctone 100.0 --name RPT-ABC
radiosync channels add -i
radiosync channels edit <id> --tmode DTCS --dtcs 023
radiosync channels list --set personal
radiosync channels show <id>
radiosync channels delete <id> [--force]
```

- Frequencies and offsets in MHz; tones in Hz; power in watts; step in kHz.
- `--duplex`: `simplex`, `+`, `-`, `split` (TX in `--tx-freq`) or `off` (RX only).
- CHIRP validates the values; a non-standard tone is accepted in the catalog, but the
  build rejects it on models that do not support it.
- Editing a memory changes every set that uses it.
- `delete` refuses if the memory belongs to any set; `--force` removes it from them.

## 5. Sets and presets

A set is an ordered list of memories. A memory can belong to several sets without being
duplicated in the catalog.

```bash
radiosync sets create scanner --description "Listening"
radiosync sets add scanner <id> <id> [--position N]
radiosync sets move scanner <id> <position>
radiosync sets member scanner <id> --alias SHORT --skip S
radiosync sets member scanner <id> --clear-alias --clear-skip
radiosync sets remove scanner <id>
radiosync sets show scanner
radiosync sets list
radiosync sets delete scanner --yes
```

- `--alias` and `--skip` apply only inside that set.
- `sets remove` and `sets delete` do not delete memories from the catalog.

A preset saves a combination of sets and, optionally, of models:

```bash
radiosync presets create daily --sets personal,repeaters [--radios <id>,<id>]
radiosync presets list
radiosync build --preset daily
```

## 6. Generate images

```bash
radiosync build                                  # every enabled model, with its default_sets
radiosync build --radio <radio-id>               # one or more models (--radio is repeatable)
radiosync build --sets personal,scanner          # combination of sets
radiosync build --output /path/to/output         # another output directory
radiosync build --dry-run -v                     # validate and show adaptations without publishing
```

Channel composition:

- `personal` goes first; the rest follow in the given order.
- A memory appears only once, in the first set that brings it; that set's alias/skip wins.
- Numbering starts at the model's first position (0 or 1, depending on the driver).
- If the channels do not fit in the model, the build fails; they are never truncated.

Output:

- `<radio-id>_<YYYYMMDD>_<hash8>.img` and `<radio-id>_<YYYYMMDD>_<hash8>.manifest.json`,
  directly in the current directory or in `--output`, without subdirectories.
- `hash8` is the first 8 characters of the image SHA-256. Sets, power and ordering are
  recorded in the [manifest](formats.md#manifest).
- If the image and its details already exist, they are reused without rewriting them; any
  other name collision adds `_2`, `_3`, ... A file is never overwritten.
- If any model in the batch fails, none is published.

## 7. Power

Power is defined by each radio, not by the channel:

1. `--power low|mid|high`: every channel at the level the profile assigns to that name.
2. Channel with its own power (for example FRS/PMR/GMRS, where the standard sets it): the
   radio level closest in watts.
3. Channel without power: the profile's `power.default` level.

```bash
radiosync build --power low
radiosync channels export --sets personal --power low --radio <radio-id>
```

## 8. Order by frequency

```bash
radiosync build --sort
radiosync channels export --sets personal,repeaters --sort --output channels.csv
```

`--sort` orders by RX frequency after removing duplicates. Channels with the same RX but a
different programming keep their relative order. Without `--sort`, the order follows the
sets. The catalog and the sets do not change.

## 9. Names and comments

**Names.** The catalog stores the full name; when generating (and when exporting CSV with
`--radio`) each name is fitted to the model:

1. Upper case if the model only supports it; invalid characters become separators.
2. If the name has a number, it is kept at the end, preceded by the whole words that fit
   (`REP-ABC-123` → `ABC123`); if none fits, the closest word is compressed
   (`NOAA-WX1` → `NWX1`).
3. Without a number, Spanish and English stopwords (de, del, la, las, el, los, y, e, of,
   the, and) are dropped and vowels are removed from the last word to the first
   (`Hill of Peace` → `HillPc`, `Cerro Alto` → `CrrAlt`), then the name is cut if it
   still does not fit.
4. If two different channels end up with the same name, the later one is numbered
   (2, 3, ...).

The changes appear as a `name_fit` adaptation in `build -v` and in the manifest.
`name_fit: false` in the profile disables name shortening.

**Comments.** In generated images and CSV files the comment starts with every set of the
memory, followed by the original comment:

```text
Sets: repeaters, repeaters-ref | Original comment
```

The catalog is not modified. On radios without native comments, CHIRP stores the comment
in the image metadata (visible in CHIRP, not on the radio display).

## 10. Validate before loading

```bash
radiosync validate                                   # latest build of each model in the current directory
radiosync validate --radio <radio-id>
radiosync validate --output /path/to/output
radiosync validate --manifest /path/to/output/<file>.manifest.json
```

Checks size and SHA-256 against the manifest and reopens the image with CHIRP to compare
every memory, special memory and setting with the expected state. Do not load an image
that fails. Then, in CHIRP: *File → Open* the image and *Radio → Upload*.

## 11. Radio settings

```bash
radiosync settings export --radio <radio-id> -o settings.json
radiosync settings diff --radio <radio-id> --from /path/to/changed.img
radiosync settings import --radio <radio-id> --from /path/to/changed.img [--dry-run]
```

Workflow: change a setting in CHIRP, save the image and run `settings import`. The profile
keeps the differences between that image and the template; the next build applies them.
You can also edit `settings` in the profile (see [formats](formats.md#radio-profile)).

## 12. Export and back up

```bash
radiosync channels export --sets personal                       # CSV with an automatic name
radiosync channels export --sets personal --output personal.csv
radiosync channels export --sets personal --radio <radio-id>    # names fitted to the model
radiosync db export                                             # whole catalog as JSON
radiosync db import catalog.json [--dry-run]
radiosync db backup
```

- Without `--output`, the file is created in the current directory with the sets and the
  date in its name.
- If the destination file exists, it is backed up before being overwritten.
- Every command that writes to the database first makes a consistent copy in the storage
  `bkp/` directory.
