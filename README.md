# radiosync

Catálogo maestro de memorias para radios programables con CHIRP. Guarda cada
programación una sola vez (SQLite), la agrupa en *sets* combinables y genera, por
**modelo** de radio, una imagen `.img` validada con sus settings, lista para cargarse
desde CHIRP.

Versión: 0.1.10

## Qué resuelve

- Una sola lista maestra para todos tus radios; cada modelo recibe su propia imagen.
- Sets reutilizables (`personal`, `repetidoras`, `scanner`, ...) que se combinan al generar.
- Importación desde CSV de CHIRP, imágenes `.img` y catálogos JSON, sin duplicar canales.
- Settings por modelo guardados en JSON y aplicados sobre una imagen descargada del radio.
- Validación antes de cargar: la imagen se vuelve a abrir con CHIRP y se compara con lo esperado.

## Instalación rápida

Requisitos: Python 3.11+, [pipx](https://pipx.pypa.io/) y CHIRP instalado en su propio
entorno (por ejemplo `pipx install chirp`).

```bash
pipx install .
radiosync init
radiosync where
```

## Inicio rápido

```bash
radiosync radios register --template /path/to/download.img
radiosync channels import /path/to/channels.csv --set personal
radiosync build --dry-run -v
radiosync build
radiosync validate
```

Los `.img` y `.manifest.json` se guardan en la carpeta actual (o en `--output`). Los datos
internos (catálogo, perfiles, templates y respaldos) viven en `~/.config/radiosync/`.

## Documentación

| Documento | Contenido |
|---|---|
| [docs/guia-de-uso.md](docs/guia-de-uso.md) | Flujo completo: modelos, importación, sets, builds, potencia, orden, nombres, validación, settings y respaldos |
| [docs/referencia-cli.md](docs/referencia-cli.md) | Todos los comandos, opciones y variables de entorno |
| [docs/arquitectura.md](docs/arquitectura.md) | Almacenamiento, proceso de CHIRP, construcción y verificación de imágenes, deduplicación |
| [docs/formatos.md](docs/formatos.md) | Perfil de radio, preset, catálogo JSON y manifiesto |
| [CHANGELOG.md](CHANGELOG.md) | Cambios por versión |

## Límites

La validación confirma lo que el driver de CHIRP puede leer y escribir; no prueba
compatibilidad de firmware, comportamiento RF ni autorización para transmitir. Usa como
template una imagen descargada del mismo modelo y revisa la imagen en CHIRP antes de cargarla.

## Desarrollo

```bash
uv sync
uv run pytest
RADIOSYNC_TEST_TEMPLATE=/path/to/download.img uv run pytest tests/test_chirp_integration.py
pipx install --force .
```

`pipx install .` copia el código; después de modificarlo, reinstala con `--force`.
