# Referencia de la CLI

`radiosync --help` y `radiosync <comando> --help` muestran la misma información.

## Opción global

| Opción | Uso |
|---|---|
| `--home <path>` | Almacenamiento interno alternativo; tiene prioridad sobre `RADIOSYNC_HOME` y `XDG_CONFIG_HOME` |

## Variables de entorno

| Variable | Uso |
|---|---|
| `RADIOSYNC_HOME` | Almacenamiento interno alternativo |
| `XDG_CONFIG_HOME` | Base del almacenamiento por defecto (`$XDG_CONFIG_HOME/radiosync`) |
| `RADIOSYNC_CHIRP_PYTHON` | Intérprete de Python del entorno de CHIRP |
| `PIPX_HOME` | Base para encontrar el entorno pipx de CHIRP |
| `RADIOSYNC_TEST_TEMPLATE` | Solo pruebas: imagen para las pruebas de integración |

## Generales

| Comando | Descripción |
|---|---|
| `init` | Crea el almacenamiento, la base y el set `personal`; muestra la versión de CHIRP |
| `where` | Muestra almacenamiento, base de datos, carpeta de salida e intérprete de CHIRP |
| `version` | Versiones de radiosync y CHIRP |

## build

```text
radiosync build [--radio <id>]... [--sets a,b | --preset <name>] [--output <dir>]
                [--power low|mid|high] [--sort] [--dry-run] [-v]
```

| Opción | Uso |
|---|---|
| `--radio <id>` | Modelo; repetible. Sin ella: todos los habilitados (o los del preset) |
| `--sets a,b` | Sets a combinar. Sin ella: `default_sets` de cada perfil |
| `--preset <name>` | Combinación guardada; excluyente con `--sets` |
| `--output`, `-o <dir>` | Carpeta de salida; por defecto la actual |
| `--power low\|mid\|high` | Todos los canales al nivel del perfil con ese nombre |
| `--sort` | Ordena por frecuencia RX en lugar de por sets |
| `--dry-run` | Construye y verifica sin publicar |
| `--verbose`, `-v` | Lista cada adaptación |

## validate

```text
radiosync validate [--radio <id>]... [--output <dir>] [--manifest <file>]...
```

| Opción | Uso |
|---|---|
| `--radio <id>` | Solo esos modelos; repetible |
| `--output`, `-o <dir>` | Carpeta donde buscar manifiestos; por defecto la actual |
| `--manifest <file>` | Manifiestos concretos; repetible |

Sin `--manifest`, valida el manifiesto más reciente de cada modelo en la carpeta.

## channels

| Comando | Opciones | Descripción |
|---|---|---|
| `import <file>` | `--set <name>`, `--dry-run` | Importa `.csv`, `.img` o catálogo `.json` |
| `export` | `--sets a,b`, `--format chirp-csv\|json`, `--output <file>`, `--radio <id>`, `--power`, `--sort` | Exporta composición CSV o catálogo JSON |
| `list` | `--set <name>`, `--search <text>` | Lista memorias o miembros de un set |
| `show <id>` | | Detalle y sets de una memoria |
| `add` | campos de memoria, `--set <name>` (repetible), `-i` | Crea una memoria |
| `edit <id>` | campos de memoria, `-i` | Modifica una memoria |
| `delete <id>` | `--force` | Borra una memoria (`--force` la quita de sus sets) |

Reglas de `export`:

- `chirp-csv` (por defecto) requiere `--sets`; `json` sin `--sets` exporta todo el catálogo.
- `--radio` adapta nombres al modelo; `--power` requiere `--radio`.
- `--radio`, `--power` y `--sort` aplican solo a `chirp-csv`.
- Sin `--output`: `<sets|catalog>__<fecha>.csv|json` en la carpeta actual.

Campos de memoria (`add` / `edit`):

| Opción | Valor |
|---|---|
| `--freq` | RX en MHz |
| `--name` | Nombre |
| `--duplex` | `simplex`, `+`, `-`, `split`, `off` |
| `--offset` | Offset en MHz (`+`/`-`) |
| `--tx-freq` | TX en MHz (`split`) |
| `--mode` | `FM`, `NFM`, `AM`, ... |
| `--tmode` | `none`, `Tone`, `TSQL`, `DTCS`, `Cross`, `TSQL-R`, `DTCS-R` |
| `--rtone` / `--ctone` | CTCSS en Hz (Tone / TSQL) |
| `--dtcs` / `--rx-dtcs` / `--polarity` | Código DCS, DCS de RX, `NN`/`NR`/`RN`/`RR` |
| `--cross-mode` | Por ejemplo `Tone->DTCS` |
| `--power` | Watts; vacío para la potencia del radio |
| `--step` | Paso en kHz; vacío para automático |
| `--skip` | vacío, `S` o `P` |
| `--comment` | Comentario |

## sets

| Comando | Opciones | Descripción |
|---|---|---|
| `create <name>` | `--description` | Crea un set vacío |
| `list` | | Sets y número de memorias |
| `show <name>` | | Miembros en orden |
| `add <name> <id>...` | `--position`, `--alias`, `--skip` | Agrega memorias |
| `remove <name> <id>...` | | Quita memorias (siguen en el catálogo) |
| `move <name> <id> <pos>` | | Cambia la posición |
| `member <name> <id>` | `--alias`, `--clear-alias`, `--skip`, `--clear-skip` | Alias/skip dentro del set |
| `delete <name>` | `--yes` | Borra el set (no las memorias) |

## radios

| Comando | Opciones | Descripción |
|---|---|---|
| `list` | | Modelos, memorias, sets por defecto, niveles de potencia |
| `register` | `--template <img>`, `--radio <id>`, `--replace` | Registra o reemplaza el template |
| `inspect` | `--radio <id>` | Capacidades y estado de la firma del driver |

## settings

| Comando | Opciones | Descripción |
|---|---|---|
| `export` | `--radio <id>`, `--output <file>` | Todos los settings del template en JSON (sin `--output`, a la terminal) |
| `diff` | `--radio <id>`, `--from <img>` | Diferencias de una imagen contra el template |
| `import` | `--radio <id>`, `--from <img>`, `--dry-run` | Copia esas diferencias al perfil |

## presets

| Comando | Opciones | Descripción |
|---|---|---|
| `list` | | Presets guardados |
| `create <name>` | `--sets a,b`, `--radios a,b`, `--description`, `--replace` | Guarda una combinación |

## db

| Comando | Opciones | Descripción |
|---|---|---|
| `backup` | | Copia consistente de la base en `bkp/` |
| `export` | `--output <file>` | Catálogo completo en JSON |
| `import <file>` | `--dry-run` | Combina un catálogo JSON con la base |
