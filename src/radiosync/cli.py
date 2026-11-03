"""radiosync cli: Typer command line for catalog, sets, radios, settings, build and validate.

Changelog:
- 0.1.9 (2026-11-01): help text for where/validate matches storage and output locations.
- 0.1.8 (2026-11-01): --sort orders build and CHIRP CSV channels by RX frequency.
- 0.1.5 (2026-11-01): internal user storage; flat outputs in cwd or --output.
- 0.1.4 (2026-11-01): chirp-csv export with --radio fits names to that model.
- 0.1.2 (2026-11-01): --power low|mid|high for build and chirp-csv export.
- 0.1.1 (2026-11-01): global --home option, 'where' command, init records the
  user default project (--set-default to change it).
- 0.1.0 (2026-11-01): initial version.
"""

import json
import sys
from decimal import Decimal, InvalidOperation
from functools import cached_property
from pathlib import Path
from typing import Annotated, Optional

import typer
from pydantic import ValidationError

from . import __version__, memory_rules
from . import build as build_mod
from . import catalog, csv_io, json_io, settings as settings_mod, sets as sets_mod, validation
from .chirp_client import ChirpClient
from .composition import compose
from .config import (RadiosyncError, backup_file, chirp_python, find_root,
                     init_project, load_project, storage_home)
from .database import Database
from .radios import load_profile, list_profiles, register, signature_path, verify_template
from .schemas import POWER_NAMES, MemoryInput, Preset

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help="Master channel catalog that generates validated CHIRP images per model.")
channels_app = typer.Typer(no_args_is_help=True, help="Catalog memories: import, export, edit.")
sets_app = typer.Typer(no_args_is_help=True, help="Ordered channel sets.")
radios_app = typer.Typer(no_args_is_help=True, help="Radio models and their templates.")
settings_app = typer.Typer(no_args_is_help=True, help="Radio settings of a model profile.")
presets_app = typer.Typer(no_args_is_help=True, help="Saved set combinations for builds.")
db_app = typer.Typer(no_args_is_help=True, help="Database backup and JSON exchange.")
app.add_typer(channels_app, name="channels")
app.add_typer(sets_app, name="sets")
app.add_typer(radios_app, name="radios")
app.add_typer(settings_app, name="settings")
app.add_typer(presets_app, name="presets")
app.add_typer(db_app, name="db")

DUPLEX_CHOICES = {"simplex": "", "": "", "+": "+", "-": "-", "split": "split", "off": "off"}
TMODE_CHOICES = {"none": "", "": "", "tone": "Tone", "tsql": "TSQL", "dtcs": "DTCS",
                 "cross": "Cross", "tsql-r": "TSQL-R", "dtcs-r": "DTCS-R"}


class Env:
    home: Path | None = None

    @cached_property
    def project(self):
        return load_project(find_root(home=self.home))

    @cached_property
    def db(self):
        database = Database(self.project)
        database.ensure_schema()
        return database

    @cached_property
    def client(self):
        return ChirpClient(chirp_python(self.project))


env = Env()


def echo(text: str = "") -> None:
    typer.echo(text)


def fail(message: str, details=()) -> None:
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    for line in details:
        typer.secho(f"  - {line}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def table(headers: list[str], rows: list[list]) -> None:
    cells = [[str(c) for c in row] for row in rows]
    widths = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(headers)]
    echo("  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip())
    echo("  ".join("-" * w for w in widths))
    for row in cells:
        echo("  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())


def split_list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def fmt_mhz(hz: int) -> str:
    return f"{hz // 1_000_000}.{hz % 1_000_000:06d}"


def fmt_tone(wire: dict) -> str:
    tmode = wire["tmode"]
    if not tmode:
        return ""
    if tmode == "Tone":
        return f"Tone {wire['rtone_dhz'] / 10}"
    if tmode in ("TSQL", "TSQL-R"):
        return f"{tmode} {wire['ctone_dhz'] / 10}"
    if tmode in ("DTCS", "DTCS-R"):
        return f"{tmode} {wire['dtcs']:03d}{wire['dtcs_polarity']}"
    return f"Cross {wire['cross_mode']}"


def fmt_duplex(wire: dict) -> str:
    duplex = wire["duplex"]
    if duplex in ("+", "-"):
        return f"{duplex}{fmt_mhz(wire['offset_hz'])}"
    if duplex == "split":
        return f"TX {fmt_mhz(wire['offset_hz'])}"
    if duplex == "off":
        return "RX only"
    return ""


def fmt_power(mw: int | None) -> str:
    return "" if mw is None else f"{Decimal(mw) / 1000:g}W"


def parse_scaled(text: str, scale: int, label: str) -> int:
    try:
        value = Decimal(text.strip().rstrip("WwMmHhKkZz")) * scale
    except InvalidOperation as exc:
        raise RadiosyncError(f"{label}: {text!r} is not a number") from exc
    if value != value.to_integral_value():
        raise RadiosyncError(f"{label}: {text!r} has too many decimals")
    return int(value)


def parse_choice(text: str, choices: dict, label: str) -> str:
    key = text.strip().lower() if text.strip().lower() in choices else text.strip()
    if key not in choices:
        raise RadiosyncError(f"{label}: {text!r} must be one of "
                             f"{', '.join(k for k in choices if k)}")
    return choices[key]


def check_power(power: str | None) -> str | None:
    if power is None:
        return None
    value = power.strip().lower()
    if value not in POWER_NAMES:
        raise RadiosyncError(f"--power must be one of {', '.join(POWER_NAMES)}")
    return value


SortSel = Annotated[bool, typer.Option(
    "--sort", help="Order generated channels by RX frequency instead of sets")]


PowerSel = Annotated[Optional[str], typer.Option(
    "--power", help="Force every channel to the radio's low, mid or high level")]


def parse_int(text: str, label: str) -> int:
    try:
        return int(str(text).strip())
    except ValueError as exc:
        raise RadiosyncError(f"{label}: {text!r} is not an integer") from exc


def run_cli(func):
    try:
        func()
    except RadiosyncError as exc:
        fail(str(exc), exc.details)
    except ValidationError as exc:
        fail("Invalid values", [f"{'.'.join(map(str, e['loc'])) or 'memory'}: {e['msg']}"
                                for e in exc.errors()])


def memory_row(memory, member=None) -> list:
    wire = catalog.memory_to_wire(memory)
    name = member.alias if member and member.alias else wire["name"]
    skip = member.skip if member and member.skip is not None else wire["skip"]
    row = [memory.id, name, fmt_mhz(wire["freq_hz"]), fmt_duplex(wire), wire["mode"],
           fmt_tone(wire), fmt_power(wire["power_mw"]), skip]
    return ([member.position] if member else []) + row


MEMORY_HEADERS = ["ID", "Name", "MHz", "Duplex", "Mode", "Tone", "Power", "Skip"]


def edit_wire(base: dict, options: dict, interactive: bool) -> dict:
    """Apply CLI options (and prompts) on top of @base; returns a wire dict."""
    wire = dict(base)
    if interactive:
        defaults = {
            "freq": fmt_mhz(wire["freq_hz"]) if wire["freq_hz"] else "",
            "name": wire["name"],
            "duplex": wire["duplex"] or "simplex",
            "offset": fmt_mhz(wire["offset_hz"]) if wire["duplex"] in ("+", "-") else "0.6",
            "tx_freq": fmt_mhz(wire["offset_hz"]) if wire["duplex"] == "split" else "",
            "mode": wire["mode"],
            "tmode": wire["tmode"] or "none",
            "rtone": str(wire["rtone_dhz"] / 10),
            "ctone": str(wire["ctone_dhz"] / 10),
            "dtcs": f"{wire['dtcs']:03d}",
            "rx_dtcs": f"{wire['rx_dtcs']:03d}",
            "polarity": wire["dtcs_polarity"],
            "cross_mode": wire["cross_mode"],
            "power": fmt_power(wire["power_mw"]),
            "step": "" if wire["tuning_step_hz"] is None else str(Decimal(wire["tuning_step_hz"]) / 1000),
            "skip": wire["skip"],
            "comment": wire["comment"],
        }
        for key in ("freq", "name", "duplex"):
            if options.get(key) is None:
                options[key] = typer.prompt(key, default=defaults[key] or None,
                                            show_default=bool(defaults[key]))
        duplex = parse_choice(options["duplex"], DUPLEX_CHOICES, "duplex")
        if duplex in ("+", "-") and options.get("offset") is None:
            options["offset"] = typer.prompt("offset MHz", default=defaults["offset"])
        if duplex == "split" and options.get("tx_freq") is None:
            options["tx_freq"] = typer.prompt("TX MHz", default=defaults["tx_freq"] or None)
        for key in ("mode", "tmode"):
            if options.get(key) is None:
                options[key] = typer.prompt(key, default=defaults[key])
        tmode = parse_choice(options["tmode"], TMODE_CHOICES, "tmode")
        if tmode == "Cross" and options.get("cross_mode") is None:
            options["cross_mode"] = typer.prompt("cross mode", default=defaults["cross_mode"])
        fields = memory_rules.active_tone_fields(
            tmode, options.get("cross_mode") or wire["cross_mode"])
        prompts = {"rtone_dhz": "rtone", "ctone_dhz": "ctone", "dtcs": "dtcs",
                   "rx_dtcs": "rx_dtcs", "dtcs_polarity": "polarity"}
        for field, key in prompts.items():
            if field in fields and options.get(key) is None:
                options[key] = typer.prompt(key, default=defaults[key])
        for key in ("power", "step", "skip", "comment"):
            if options.get(key) is None:
                options[key] = typer.prompt(key, default=defaults[key], show_default=True)

    if options.get("freq") is not None:
        wire["freq_hz"] = parse_scaled(options["freq"], 1_000_000, "freq")
    if options.get("name") is not None:
        wire["name"] = options["name"]
    if options.get("duplex") is not None:
        wire["duplex"] = parse_choice(options["duplex"], DUPLEX_CHOICES, "duplex")
    if options.get("offset") is not None and wire["duplex"] in ("+", "-"):
        wire["offset_hz"] = parse_scaled(options["offset"], 1_000_000, "offset")
    if options.get("tx_freq") is not None and wire["duplex"] == "split":
        wire["offset_hz"] = parse_scaled(options["tx_freq"], 1_000_000, "tx-freq")
    if options.get("mode") is not None:
        wire["mode"] = options["mode"].strip().upper()
    if options.get("tmode") is not None:
        wire["tmode"] = parse_choice(options["tmode"], TMODE_CHOICES, "tmode")
    if options.get("cross_mode") is not None:
        wire["cross_mode"] = options["cross_mode"].strip()
    if options.get("rtone") is not None:
        wire["rtone_dhz"] = parse_scaled(options["rtone"], 10, "rtone")
    if options.get("ctone") is not None:
        wire["ctone_dhz"] = parse_scaled(options["ctone"], 10, "ctone")
    if options.get("dtcs") is not None:
        wire["dtcs"] = parse_int(options["dtcs"], "dtcs")
    if options.get("rx_dtcs") is not None:
        wire["rx_dtcs"] = parse_int(options["rx_dtcs"], "rx-dtcs")
    if options.get("polarity") is not None:
        wire["dtcs_polarity"] = options["polarity"].strip().upper()
    if options.get("power") is not None:
        text = options["power"].strip()
        wire["power_mw"] = parse_scaled(text, 1000, "power") if text else None
    if options.get("step") is not None:
        text = options["step"].strip()
        wire["tuning_step_hz"] = parse_scaled(text, 1000, "step") if text else None
    if options.get("skip") is not None:
        wire["skip"] = options["skip"].strip().upper()
    if options.get("comment") is not None:
        wire["comment"] = options["comment"]
    return MemoryInput(**wire).model_dump()


def normalized(wire: dict) -> dict:
    result = env.client.normalize([wire])[0]
    return {f: result[f] for f in memory_rules.WIRE_FIELDS}


FreqOpt = Annotated[Optional[str], typer.Option("--freq", help="RX frequency in MHz")]
NameOpt = Annotated[Optional[str], typer.Option("--name")]
DuplexOpt = Annotated[Optional[str], typer.Option("--duplex", help="simplex, +, -, split, off")]
OffsetOpt = Annotated[Optional[str], typer.Option("--offset", help="Repeater offset in MHz")]
TxOpt = Annotated[Optional[str], typer.Option("--tx-freq", help="TX MHz for split")]
ModeOpt = Annotated[Optional[str], typer.Option("--mode", help="FM, NFM, AM ...")]
TmodeOpt = Annotated[Optional[str], typer.Option("--tmode",
                                                 help="none, Tone, TSQL, DTCS, Cross")]
RtoneOpt = Annotated[Optional[str], typer.Option("--rtone", help="TX CTCSS Hz (Tone)")]
CtoneOpt = Annotated[Optional[str], typer.Option("--ctone", help="CTCSS Hz (TSQL)")]
DtcsOpt = Annotated[Optional[str], typer.Option("--dtcs")]
RxDtcsOpt = Annotated[Optional[str], typer.Option("--rx-dtcs")]
PolOpt = Annotated[Optional[str], typer.Option("--polarity", help="NN, NR, RN, RR")]
CrossOpt = Annotated[Optional[str], typer.Option("--cross-mode", help="e.g. Tone->DTCS")]
PowerOpt = Annotated[Optional[str], typer.Option("--power", help="Watts, empty for default")]
StepOpt = Annotated[Optional[str], typer.Option("--step", help="Tuning step kHz")]
SkipOpt = Annotated[Optional[str], typer.Option("--skip", help="'', S or P")]
CommentOpt = Annotated[Optional[str], typer.Option("--comment")]


@app.callback()
def global_options(
        home: Annotated[Optional[Path], typer.Option(
            "--home", help="Internal storage directory (overrides RADIOSYNC_HOME and XDG_CONFIG_HOME)")] = None) -> None:
    global env
    env = Env()
    env.home = home


@app.command()
def init() -> None:
    """Initialize application storage and the default personal set."""
    def run():
        project = init_project(storage_home(env.home))
        env.__dict__["project"] = project
        with env.db.session(write=True) as session:
            _, created = sets_mod.get_or_create_set(session, "personal")
        echo(f"Storage: {project.root}")
        echo(f"Database: {project.database}")
        echo(f"CHIRP: {env.client.version()} ({chirp_python(project)})")
        echo("Set 'personal' " + ("created" if created else "already present"))
    run_cli(run)


@app.command()
def where() -> None:
    """Show the storage directory, database, output directory and CHIRP interpreter."""
    def run():
        project = env.project
        echo(f"Storage:   {project.root}")
        echo(f"Database:  {project.database}")
        echo(f"Output:    {Path.cwd()} (unless --output is specified)")
        echo(f"CHIRP:     {chirp_python(project)}")
    run_cli(run)


@app.command()
def version() -> None:
    """Show radiosync and CHIRP versions."""
    def run():
        echo(f"radiosync {__version__}")
        echo(f"CHIRP {env.client.version()}")
    run_cli(run)


@channels_app.command("import")
def channels_import(
        file: Annotated[Path, typer.Argument(help="CHIRP .csv, CHIRP .img or radiosync .json")],
        set_name: Annotated[Optional[str], typer.Option("--set", help="Add memories to set")] = None,
        dry_run: Annotated[bool, typer.Option("--dry-run")] = False) -> None:
    """Import memories; identical programmings are reused, not duplicated."""
    def run():
        if set_name:
            sets_mod.validate_name(set_name)
        notes = []
        if file.suffix.lower() == ".json":
            data = json_io.read_catalog(file)
            with env.db.session(write=not dry_run) as session:
                report, notes = json_io.import_catalog(session, env.client, data, set_name)
                if dry_run:
                    session.rollback()
            source = {"type": "catalog"}
        else:
            source, wires = csv_io.read_channels(env.client, file)
            wires = [{f: w[f] for f in memory_rules.WIRE_FIELDS} for w in wires]
            with env.db.session(write=not dry_run) as session:
                report = catalog.import_memories(session, wires, set_name, file.name)
                if dry_run:
                    session.rollback()
        label = "Dry run, nothing saved" if dry_run else "Imported"
        echo(f"{label}: {file.name} ({source['type']})")
        table(["Read", "New", "Existing", "Repeated in file", "Added to set", "Already in set"],
              [[report.read, report.new, report.existing, report.duplicates_in_file,
                report.memberships_added, report.already_members]])
        if report.set_created:
            echo(f"Set {set_name!r} " + ("would be created" if dry_run else "created"))
        for note in notes:
            echo(f"- {note}")
        if report.conflicts:
            echo("Kept existing values (programming identical, details differ):")
            for line in report.conflicts:
                echo(f"  {line}")
    run_cli(run)


@channels_app.command("export")
def channels_export(
        output: Annotated[Optional[Path], typer.Option("--output", "-o")] = None,
        sets: Annotated[Optional[str], typer.Option("--sets", help="Comma list; json: all if empty")] = None,
        fmt: Annotated[str, typer.Option("--format", help="chirp-csv or json")] = "chirp-csv",
        power: PowerSel = None,
        radio_id: Annotated[Optional[str], typer.Option(
            "--radio", help="Model to adapt names and --power to")] = None,
        sort: SortSel = False) -> None:
    """Export a composition as CHIRP CSV, or catalog/sets as JSON."""
    def run():
        names = split_list(sets)
        destination = output or Path.cwd() / (
            f"{'+' .join(names) or 'catalog'}__{build_mod.timestamp()}."
            + ("json" if fmt == "json" else "csv"))
        level = check_power(power)
        if level and not radio_id:
            raise RadiosyncError("--power needs --radio")
        if sort and fmt != "chirp-csv":
            raise RadiosyncError("--sort applies to --format chirp-csv")
        if radio_id and fmt != "chirp-csv":
            raise RadiosyncError("--radio and --power apply to --format chirp-csv")
        level_mw = None
        if level:
            profile = load_profile(env.project, radio_id)
            label = profile.power.levels.get(level)
            sig = json.loads(signature_path(env.project, radio_id).read_text())
            watts = {name: mw for name, mw in sig["valid_power_levels"]}
            if label not in watts:
                raise RadiosyncError(f"{radio_id} has no '{level}' power level")
            level_mw = watts[label]
        with env.db.session() as session:
            if fmt == "json":
                data = json_io.export_catalog(session, names or None)
                backup = backup_file(env.project, destination)
                json_io.write_catalog(data, destination)
                count = len(data.memories)
            elif fmt == "chirp-csv":
                if not names:
                    raise RadiosyncError("--sets is required for chirp-csv")
                composition = compose(session, names, sort)
                backup = backup_file(env.project, destination)
                wires = [dict(c.wire) for c in composition.channels]
                if radio_id:
                    wires, _ = build_mod.fitted_wires(env.project, load_profile(env.project, radio_id), wires)
                if level_mw is not None:
                    for wire in wires:
                        wire["power_mw"] = level_mw
                count = csv_io.write_csv(env.client, destination, wires)
            else:
                raise RadiosyncError("--format must be chirp-csv or json")
        if backup:
            echo(f"Previous file backed up to {backup}")
        echo(f"Wrote {count} memories to {destination}")
    run_cli(run)


@channels_app.command("list")
def channels_list(
        set_name: Annotated[Optional[str], typer.Option("--set")] = None,
        search: Annotated[Optional[str], typer.Option("--search")] = None) -> None:
    """List catalog memories, or the members of a set in order."""
    def run():
        with env.db.session() as session:
            rows = catalog.list_memories(session, set_name, search)
            headers = (["Pos"] if set_name else []) + MEMORY_HEADERS
            table(headers, [memory_row(m, member) for m, member in rows])
            echo(f"{len(rows)} memories")
    run_cli(run)


@channels_app.command("show")
def channels_show(memory_id: int) -> None:
    """Show every field of a memory and the sets that use it."""
    def run():
        with env.db.session() as session:
            memory = catalog.get_memory(session, memory_id)
            wire = catalog.memory_to_wire(memory)
            echo(f"#{memory.id}  {wire['name']!r}")
            echo(f"  RX        {fmt_mhz(wire['freq_hz'])} MHz")
            echo(f"  Duplex    {fmt_duplex(wire) or 'simplex'}")
            echo(f"  Mode      {wire['mode']}")
            echo(f"  Tone      {fmt_tone(wire) or 'none'}")
            echo(f"  Power     {fmt_power(wire['power_mw']) or 'radio default'}")
            step = wire["tuning_step_hz"]
            echo(f"  Step      {'auto' if step is None else f'{Decimal(step) / 1000:g} kHz'}")
            echo(f"  Skip      {wire['skip'] or '-'}")
            echo(f"  Comment   {wire['comment']}")
            echo(f"  Identity  {memory.fingerprint[:16]}")
            for member in memory.memberships:
                alias = f" as {member.alias!r}" if member.alias else ""
                echo(f"  In set    {member.channel_set.name} #{member.position}{alias}")
    run_cli(run)


@channels_app.command("add")
def channels_add(
        freq: FreqOpt = None, name: NameOpt = None, duplex: DuplexOpt = None,
        offset: OffsetOpt = None, tx_freq: TxOpt = None, mode: ModeOpt = None,
        tmode: TmodeOpt = None, rtone: RtoneOpt = None, ctone: CtoneOpt = None,
        dtcs: DtcsOpt = None, rx_dtcs: RxDtcsOpt = None, polarity: PolOpt = None,
        cross_mode: CrossOpt = None, power: PowerOpt = None, step: StepOpt = None,
        skip: SkipOpt = None, comment: CommentOpt = None,
        set_names: Annotated[Optional[list[str]], typer.Option("--set")] = None,
        interactive: Annotated[bool, typer.Option("--interactive", "-i")] = False) -> None:
    """Add a memory manually (options, or prompts with -i)."""
    def run():
        options = dict(freq=freq, name=name, duplex=duplex, offset=offset, tx_freq=tx_freq,
                       mode=mode, tmode=tmode, rtone=rtone, ctone=ctone, dtcs=dtcs,
                       rx_dtcs=rx_dtcs, polarity=polarity, cross_mode=cross_mode,
                       power=power, step=step, skip=skip, comment=comment)
        if freq is None and not interactive:
            raise RadiosyncError("--freq is required (or use --interactive)")
        base = MemoryInput(freq_hz=1).model_dump()
        base["freq_hz"] = 0
        wire = normalized(edit_wire(base, options, interactive))
        with env.db.session(write=True) as session:
            memory = catalog.add_memory(session, wire)
            for set_name in set_names or []:
                channel_set, _ = sets_mod.get_or_create_set(session, set_name)
                sets_mod.add_member(session, channel_set, memory)
            echo(f"Added #{memory.id} {memory.name!r} {fmt_mhz(memory.freq_hz)} MHz"
                 + (f" to {', '.join(set_names)}" if set_names else ""))
    run_cli(run)


@channels_app.command("edit")
def channels_edit(
        memory_id: int, freq: FreqOpt = None, name: NameOpt = None, duplex: DuplexOpt = None,
        offset: OffsetOpt = None, tx_freq: TxOpt = None, mode: ModeOpt = None,
        tmode: TmodeOpt = None, rtone: RtoneOpt = None, ctone: CtoneOpt = None,
        dtcs: DtcsOpt = None, rx_dtcs: RxDtcsOpt = None, polarity: PolOpt = None,
        cross_mode: CrossOpt = None, power: PowerOpt = None, step: StepOpt = None,
        skip: SkipOpt = None, comment: CommentOpt = None,
        interactive: Annotated[bool, typer.Option("--interactive", "-i")] = False) -> None:
    """Edit a memory; every set that uses it sees the change."""
    def run():
        options = dict(freq=freq, name=name, duplex=duplex, offset=offset, tx_freq=tx_freq,
                       mode=mode, tmode=tmode, rtone=rtone, ctone=ctone, dtcs=dtcs,
                       rx_dtcs=rx_dtcs, polarity=polarity, cross_mode=cross_mode,
                       power=power, step=step, skip=skip, comment=comment)
        with env.db.session(write=True) as session:
            memory = catalog.get_memory(session, memory_id)
            wire = normalized(edit_wire(catalog.memory_to_wire(memory), options, interactive))
            catalog.update_memory(session, memory, wire)
            echo(f"Updated #{memory.id} {memory.name!r} {fmt_mhz(memory.freq_hz)} MHz")
    run_cli(run)


@channels_app.command("delete")
def channels_delete(memory_id: int,
                    force: Annotated[bool, typer.Option("--force",
                                                        help="Also remove from sets")] = False) -> None:
    """Delete a memory from the catalog."""
    def run():
        with env.db.session(write=True) as session:
            memory = catalog.get_memory(session, memory_id)
            removed = catalog.delete_memory(session, memory, force)
            echo(f"Deleted #{memory_id}" + (f", removed from {', '.join(removed)}" if removed else ""))
    run_cli(run)


@sets_app.command("create")
def sets_create(name: str, description: Annotated[str, typer.Option()] = "") -> None:
    """Create an empty set."""
    def run():
        with env.db.session(write=True) as session:
            sets_mod.create_set(session, name, description)
        echo(f"Set {name!r} created")
    run_cli(run)


@sets_app.command("list")
def sets_list() -> None:
    """List sets with their sizes."""
    def run():
        with env.db.session() as session:
            table(["Set", "Memories", "Description"],
                  [[s.name, n, s.description] for s, n in sets_mod.list_sets(session)])
    run_cli(run)


@sets_app.command("show")
def sets_show(name: str) -> None:
    """Show the members of a set in order."""
    channels_list(set_name=name, search=None)


@sets_app.command("add")
def sets_add(name: str, memory_ids: list[int],
             position: Annotated[Optional[int], typer.Option()] = None,
             alias: Annotated[Optional[str], typer.Option(help="Name used in this set")] = None,
             skip: Annotated[Optional[str], typer.Option(help="Skip used in this set")] = None) -> None:
    """Add memories to a set (appended, or inserted at --position)."""
    def run():
        with env.db.session(write=True) as session:
            channel_set = sets_mod.get_set(session, name)
            for offset, memory_id in enumerate(memory_ids):
                memory = catalog.get_memory(session, memory_id)
                pos = None if position is None else position + offset
                sets_mod.add_member(session, channel_set, memory, pos, alias, skip)
        echo(f"Added {len(memory_ids)} memories to {name!r}")
    run_cli(run)


@sets_app.command("remove")
def sets_remove(name: str, memory_ids: list[int]) -> None:
    """Remove memories from a set; they stay in the catalog."""
    def run():
        with env.db.session(write=True) as session:
            channel_set = sets_mod.get_set(session, name)
            for memory_id in memory_ids:
                sets_mod.remove_member(session, channel_set, catalog.get_memory(session, memory_id))
        echo(f"Removed {len(memory_ids)} memories from {name!r}")
    run_cli(run)


@sets_app.command("move")
def sets_move(name: str, memory_id: int, position: int) -> None:
    """Move a member to a new position."""
    def run():
        with env.db.session(write=True) as session:
            channel_set = sets_mod.get_set(session, name)
            sets_mod.move_member(session, channel_set, catalog.get_memory(session, memory_id),
                                 position)
        echo(f"Moved #{memory_id} to position {position} in {name!r}")
    run_cli(run)


@sets_app.command("member")
def sets_member(name: str, memory_id: int,
                alias: Annotated[Optional[str], typer.Option()] = None,
                clear_alias: Annotated[bool, typer.Option("--clear-alias")] = False,
                skip: Annotated[Optional[str], typer.Option()] = None,
                clear_skip: Annotated[bool, typer.Option("--clear-skip")] = False) -> None:
    """Set or clear the alias/skip a memory uses inside one set."""
    def run():
        changes = {}
        if alias is not None or clear_alias:
            changes["alias"] = None if clear_alias else alias
        if skip is not None or clear_skip:
            if skip is not None and skip.upper() not in memory_rules.SKIP_VALUES:
                raise RadiosyncError("--skip must be '', S or P")
            changes["skip"] = None if clear_skip else skip.upper()
        if not changes:
            raise RadiosyncError("Nothing to change")
        with env.db.session(write=True) as session:
            channel_set = sets_mod.get_set(session, name)
            sets_mod.update_member(session, channel_set, catalog.get_memory(session, memory_id),
                                   **changes)
        echo(f"Updated #{memory_id} in {name!r}")
    run_cli(run)


@sets_app.command("delete")
def sets_delete(name: str, yes: Annotated[bool, typer.Option("--yes")] = False) -> None:
    """Delete a set; its memories stay in the catalog."""
    def run():
        if not yes:
            typer.confirm(f"Delete set {name!r}?", abort=True)
        with env.db.session(write=True) as session:
            count = sets_mod.delete_set(session, name)
        echo(f"Set {name!r} deleted ({count} memberships removed)")
    run_cli(run)


@radios_app.command("list")
def radios_list() -> None:
    """List registered models."""
    def run():
        rows = []
        for profile in list_profiles(env.project):
            sig = signature_path(env.project, profile.id)
            lo, hi = json.loads(sig.read_text())["memory_bounds"] if sig.is_file() else ("?", "?")
            rows.append([profile.id, f"{profile.identity.vendor} {profile.identity.model}",
                         "yes" if profile.enabled else "no", f"{lo}-{hi}",
                         ",".join(profile.default_sets), len(profile.settings),
                         "/".join(profile.power.levels.get(n, "-") for n in POWER_NAMES)
                         + f" ({profile.power.default})",
                         profile.template.chirp_version])
        table(["Radio", "Model", "Enabled", "Memories", "Default sets", "Settings",
               "Power low/mid/high (default)", "CHIRP"], rows)
    run_cli(run)


@radios_app.command("register")
def radios_register(
        template: Annotated[Path, typer.Option("--template", help="Image downloaded from the radio")],
        radio_id: Annotated[Optional[str], typer.Option("--radio", help="Id; default from model")] = None,
        replace: Annotated[bool, typer.Option("--replace")] = False) -> None:
    """Register (or replace) the template image of a model."""
    def run():
        profile, info, backups = register(env.project, env.client, template.resolve(),
                                          radio_id, replace)
        lo, hi = info["signature"]["memory_bounds"]
        echo(f"Registered {profile.id}: {profile.identity.vendor} {profile.identity.model}")
        echo(f"  Memories {lo}-{hi}, name length {info['signature']['valid_name_length']}, "
             f"power {', '.join(p for p, _ in info['signature']['valid_power_levels'])}")
        echo(f"  Template {profile.template.file} (CHIRP {profile.template.chirp_version})")
        echo(f"  Channel extras: {json.dumps(profile.extras)}")
        for backup in backups:
            echo(f"  Backup {backup}")
    run_cli(run)


@radios_app.command("inspect")
def radios_inspect(radio_id: Annotated[str, typer.Option("--radio")]) -> None:
    """Show capabilities and check the template against the registered signature."""
    def run():
        profile = load_profile(env.project, radio_id)
        info = env.client.inspect(verify_template(env.project, profile))
        sig = info["signature"]
        echo(f"{profile.id}: {info['identity']}")
        echo(f"  Memories        {sig['memory_bounds'][0]}-{sig['memory_bounds'][1]} "
             f"({info['memories_used']} used in template)")
        echo(f"  Name length     {sig['valid_name_length']}")
        echo(f"  Power levels    {', '.join(f'{p} ({mw / 1000:g}W)' for p, mw in sig['valid_power_levels'])}")
        echo(f"  Modes           {', '.join(sig['valid_modes'])}")
        echo(f"  Duplex          {', '.join(d or 'simplex' for d in sig['valid_duplexes'])}")
        echo(f"  Bands MHz       {', '.join(f'{lo / 1e6:g}-{hi / 1e6:g}' for lo, hi in sig['valid_bands'])}")
        echo(f"  Special memories {', '.join(sig['valid_special_chans']) or 'none'}")
        echo(f"  Extras          {', '.join(e['name'] for e in info['extras']) or 'none'}")
        echo(f"  Settings        {len(info['settings'])} ({len(profile.settings)} overridden)")
        same = info["signature_sha256"] == profile.template.signature_sha256
        echo(f"  Signature       {'matches registration' if same else 'CHANGED since registration'}"
             f" (CHIRP now {info['chirp_version']}, registered {profile.template.chirp_version})")
        if not same:
            raise RadiosyncError("Driver capabilities changed; review and re-register with --replace")
    run_cli(run)


@settings_app.command("export")
def settings_export(radio_id: Annotated[str, typer.Option("--radio")],
                    output: Annotated[Optional[Path], typer.Option("--output", "-o")] = None) -> None:
    """Dump every setting of the template (path, type, value, options) as JSON."""
    def run():
        data = settings_mod.export_settings(env.project, env.client, radio_id)
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if output is None:
            sys.stdout.write(text)
            return
        backup = backup_file(env.project, output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text)
        echo(f"Wrote {len(data['settings'])} settings to {output}"
             + (f" (backup {backup})" if backup else ""))
    run_cli(run)


@settings_app.command("diff")
def settings_diff(radio_id: Annotated[str, typer.Option("--radio")],
                  image: Annotated[Path, typer.Option("--from", help="Image to compare")]) -> None:
    """Show settings where an image differs from the registered template."""
    def run():
        diffs = settings_mod.diff_image(env.project, env.client, radio_id, image)
        table(["Setting", "Template", "Image", "Profile", "Writable"],
              [[d["path"], d["template"], d["image"],
                "" if d["profile"] is None else d["profile"],
                "yes" if d["mutable"] and d["overridable"] else "no"] for d in diffs])
        echo(f"{len(diffs)} differences")
    run_cli(run)


@settings_app.command("import")
def settings_import(radio_id: Annotated[str, typer.Option("--radio")],
                    image: Annotated[Path, typer.Option("--from", help="Image with the wanted settings")],
                    dry_run: Annotated[bool, typer.Option("--dry-run")] = False) -> None:
    """Make the profile settings equal to an image's settings (differences vs template)."""
    def run():
        overrides, usable, skipped, backup = settings_mod.import_from_image(
            env.project, env.client, radio_id, image, dry_run)
        table(["Setting", "Template", "New value"],
              [[d["path"], d["template"], d["image"]] for d in usable])
        for d in skipped:
            echo(f"Not writable, ignored: {d['path']}")
        echo(("Dry run: " if dry_run else "Saved: ") + f"{len(overrides)} overrides"
             + (f" (backup {backup})" if backup else ""))
    run_cli(run)


@presets_app.command("list")
def presets_list() -> None:
    """List presets."""
    def run():
        rows = []
        for path in sorted(env.project.presets.glob("*.json")):
            preset = build_mod.load_preset(env.project, path.stem)
            rows.append([path.stem, ",".join(preset.sets), ",".join(preset.radios or ["all"]),
                         preset.description])
        table(["Preset", "Sets", "Radios", "Description"], rows)
    run_cli(run)


@presets_app.command("create")
def presets_create(name: str,
                   sets: Annotated[str, typer.Option("--sets", help="Comma list")],
                   radios: Annotated[Optional[str], typer.Option("--radios", help="Comma list")] = None,
                   description: Annotated[str, typer.Option()] = "",
                   replace: Annotated[bool, typer.Option("--replace")] = False) -> None:
    """Save a set combination (and optional radios) under a name."""
    def run():
        sets_mod.validate_name(name)
        path = env.project.presets / f"{name}.json"
        if path.exists() and not replace:
            raise RadiosyncError(f"Preset {name!r} exists; use --replace")
        preset = Preset(description=description, sets=split_list(sets),
                        radios=split_list(radios) or None)
        with env.db.session() as session:
            compose(session, preset.sets)
        for radio in preset.radios or []:
            load_profile(env.project, radio)
        backup = backup_file(env.project, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(preset.model_dump_json(indent=2) + "\n")
        echo(f"Preset {name!r} saved" + (f" (backup {backup})" if backup else ""))
    run_cli(run)


@db_app.command("backup")
def db_backup() -> None:
    """Consistent copy of the database into the backup directory."""
    def run():
        echo(f"Backup: {env.db.backup()}")
    run_cli(run)


@db_app.command("export")
def db_export(output: Annotated[Optional[Path], typer.Option("--output", "-o")] = None) -> None:
    """Export the whole catalog and all sets as JSON."""
    channels_export(output=output, sets=None, fmt="json", power=None, radio_id=None, sort=False)


@db_app.command("import")
def db_import(file: Path, dry_run: Annotated[bool, typer.Option("--dry-run")] = False) -> None:
    """Merge a radiosync JSON catalog into the database."""
    channels_import(file=file, set_name=None, dry_run=dry_run)


@app.command("build")
def build_cmd(
        radios: Annotated[Optional[list[str]], typer.Option("--radio", help="Model id; repeatable")] = None,
        sets: Annotated[Optional[str], typer.Option("--sets", help="Comma list of sets")] = None,
        preset: Annotated[Optional[str], typer.Option("--preset")] = None,
        output: Annotated[Optional[Path], typer.Option("--output", "-o")] = None,
        dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate without publishing")] = False,
        power: PowerSel = None,
        sort: SortSel = False,
        verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    """Generate validated images for one, several or all models."""
    def run():
        level = check_power(power)
        with env.db.session() as session:
            targets = build_mod.plan(env.project, session, radios or [],
                                     split_list(sets) or None, preset, level, sort)
        results = build_mod.run(env.project, env.client, targets, dry_run, output)
        failed = [r for r in results if not r.ok]
        for item in results:
            target = item.target
            head = (f"{target.profile.id}: {len(target.composition.channels)} channels from "
                    f"{'+'.join(target.composition.sets)}"
                    + (f", power {target.power} ({target.profile.power.levels[target.power]})"
                       if target.power else "")
                    + (", sorted by frequency" if sort else ""))
            if not item.ok:
                typer.secho(f"FAILED {head}: {item.error}", fg=typer.colors.RED)
                for line in item.details[:40]:
                    echo(f"    {line}")
                if len(item.details) > 40:
                    echo(f"    ... {len(item.details) - 40} more")
                continue
            result = item.result
            kinds = {}
            for a in result["adaptations"]:
                kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
            status = "OK (dry run)" if dry_run else "OK (not published)" if failed else "OK"
            typer.secho(f"{status} {head}", fg=typer.colors.GREEN)
            if kinds:
                echo(f"    adaptations: {', '.join(f'{k} {n}' for k, n in sorted(kinds.items()))}")
            if result["settings_applied"]:
                echo(f"    settings applied: {len(result['settings_applied'])}")
            for note in target.composition.notes:
                echo(f"    note: {note}")
            if result["validation_warnings"]:
                echo(f"    CHIRP warnings: {len(result['validation_warnings'])}")
            if verbose:
                for a in result["adaptations"]:
                    echo(f"    [{a['number']}] {a['kind']}: {a['before']} -> {a['after']}")
            if item.image and item.manifest:
                echo(f"    image: {item.image}")
        if failed:
            raise RadiosyncError(f"{len(failed)} of {len(results)} builds failed; nothing published")
    run_cli(run)


@app.command("validate")
def validate_cmd(
        radios: Annotated[Optional[list[str]], typer.Option("--radio", help="Model id; repeatable")] = None,
        manifests: Annotated[Optional[list[Path]], typer.Option("--manifest")] = None,
        output: Annotated[Optional[Path], typer.Option("--output", "-o")] = None) -> None:
    """Re-check generated images (latest per model in the current directory or --output)."""
    def run():
        paths = list(manifests or []) or validation.latest_manifests(env.project, radios, output)
        bad = 0
        for path in paths:
            result = validation.validate(env.client, path)
            name = result.image.name if result.image else path.name
            if result.ok:
                typer.secho(f"OK     {name}", fg=typer.colors.GREEN)
            else:
                bad += 1
                typer.secho(f"FAILED {name}", fg=typer.colors.RED)
                for line in result.problems[:40]:
                    echo(f"    {line}")
            for note in result.notes:
                echo(f"    note: {note}")
        if bad:
            raise RadiosyncError(f"{bad} of {len(paths)} images failed validation; do not upload them")
    run_cli(run)


def main() -> None:
    app()
