# Arquitectura

## Componentes

| Módulo | Responsabilidad |
|---|---|
| `cli.py` | Comandos (Typer) |
| `config.py` | Almacenamiento, intérprete de CHIRP, respaldos |
| `database.py`, `models.py`, `migrations/` | SQLite con SQLAlchemy y Alembic |
| `memory_rules.py` | Forma canónica e identidad de una programación |
| `catalog.py`, `sets.py` | Memorias, importación con deduplicación, sets |
| `composition.py` | Combinación de sets, comentarios y orden |
| `names.py` | Adaptación de nombres al modelo |
| `radios.py`, `settings.py` | Perfiles, templates, settings |
| `build.py`, `validation.py` | Generación, publicación y verificación |
| `csv_io.py`, `json_io.py` | Intercambio CSV/imagen y catálogo JSON |
| `chirp_client.py`, `chirp_worker.py` | Puente con CHIRP en un proceso aparte |

## Almacenamiento

Los datos internos viven fuera del código:

```text
~/.config/radiosync/            ($XDG_CONFIG_HOME/radiosync, RADIOSYNC_HOME o --home)
├── config.toml                 rutas internas y [chirp] python
├── radios/<id>.json            perfil por modelo
├── presets/<name>.json         combinaciones guardadas
├── data/radiosync.db           catálogo y sets
├── templates/<id>.img          imagen base registrada
├── templates/<id>.signature.json  capacidades del driver al registrar
└── bkp/                        respaldos
```

Prioridad para elegir el almacenamiento: `--home`, `RADIOSYNC_HOME`, luego
`$XDG_CONFIG_HOME/radiosync` o `~/.config/radiosync`. La carpeta actual nunca selecciona
otro catálogo; solo es el destino por defecto de builds y exportaciones.

`config.toml`:

```toml
[paths]
database = "data/radiosync.db"
templates = "templates"
backups = "bkp"
radios = "radios"
presets = "presets"

[chirp]
python = "/path/to/chirp/venv/bin/python"   # opcional
```

Intérprete de CHIRP, en este orden: `RADIOSYNC_CHIRP_PYTHON`, `[chirp] python` de
`config.toml` y el entorno pipx de CHIRP (`$PIPX_HOME/venvs/chirp`,
`~/.local/share/pipx/venvs/chirp`, `~/.local/pipx/venvs/chirp`).

## Respaldos

| Qué | Cuándo | Cómo |
|---|---|---|
| Base de datos | Antes de cada comando que escribe y antes de migrar el esquema | API de backup de SQLite |
| Perfil de radio | Antes de sobrescribirlo | Copia |
| Template y firma | `radios register --replace` | Copia |
| Preset / archivo exportado | Antes de sobrescribirlo | Copia |

Formato: `bkp/<archivo>.bkp-<YYMMDDHHmmss>` (con `-1`, `-2`, ... si coincide el segundo).

## Puente con CHIRP

radiosync no importa CHIRP. `chirp_client.py` ejecuta `chirp_worker.py` con el intérprete
de CHIRP (`python -I -B`), le envía una petición JSON por stdin y lee una respuesta JSON
por stdout. El worker no abre puertos serie: solo lee imágenes/CSV y escribe archivos nuevos.

| Operación | Uso |
|---|---|
| `version` | Versión de CHIRP |
| `inspect` | Identidad, capacidades, firma, extras y settings de una imagen |
| `read_channels` | Memorias de un CSV o imagen |
| `normalize` | Valida y normaliza memorias con las reglas de CHIRP |
| `write_csv` | Escribe un CSV con el driver genérico de CHIRP |
| `build` | Genera y verifica una imagen |
| `verify` | Compara una imagen con el estado esperado |
| `settings_diff` | Diferencias de settings entre dos imágenes |

El worker ejecuta `gettext.install("CHIRP")` antes de cargar los drivers: algunos drivers
usan `_()`, que solo define la interfaz gráfica de CHIRP.

## Identidad de una memoria

`memory_rules.py` define la forma canónica y el fingerprint (SHA-256):

- Forman la identidad: frecuencia RX, duplex, offset/TX, modo, modo de tono y los
  tonos/DTCS **activos** para ese modo, polaridad y cross mode cuando aplican.
- No forman la identidad: nombre, comentario, potencia, skip y paso.
- Los tonos inactivos se normalizan, así dos programaciones RF iguales comparan igual.
- El fingerprint es único en la base: importar una programación existente la reutiliza.

Unidades internas: Hz (frecuencias y offsets), décimas de Hz (CTCSS), mW (potencia).

## Construcción de una imagen

Por cada modelo, en una carpeta temporal:

1. Verifica el SHA-256 del template y que la firma de capacidades del driver no cambió.
2. Compone los sets: deduplica, aplica alias/skip, comentarios `Sets: ...` y `--sort`.
3. Adapta los nombres al modelo (`names.py`).
4. Para cada canal, `import_logic.import_mem` de CHIRP lo adapta al modelo; ajusta el paso
   si hace falta y compara antes/después contra `allowed_adaptations`; ejecuta
   `validate_memory` del driver.
5. Aplica potencia (forzada, del canal o `power.default`) y `extras` del perfil.
6. Escribe la memoria, la vuelve a leer y compara lo guardado.
7. Borra las memorias ordinarias sobrantes; no toca memorias especiales (VFO).
8. Aplica settings solo si alguno cambia, igual que la interfaz de CHIRP.
9. Verifica que ningún otro setting ni memoria especial cambió.
10. Guarda la imagen, la recarga y compara memorias, especiales y settings de nuevo.

Si todos los modelos pasan, se publican `.img` y manifiesto en el destino; si uno falla,
no se publica ninguno. `validate` repite la comparación del paso 10 contra el manifiesto.

La validación confirma lo que el driver puede leer y escribir; no prueba firmware,
comportamiento RF ni autorización para transmitir.

## Migraciones

El esquema se versiona con Alembic (`src/radiosync/migrations/`). La aplicación aplica las
migraciones pendientes al abrir la base, después de respaldarla. Para uso manual desde el
repositorio, `alembic` usa la base del almacenamiento activo:

```bash
uv run alembic current
```
