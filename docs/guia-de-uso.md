# Guía de uso

Flujo completo de radiosync, de registrar un modelo a cargar la imagen en el radio. Las
rutas y nombres son ejemplos: sustitúyelos por los tuyos.

## 1. Inicializar

```bash
radiosync init
radiosync where
```

`init` crea el almacenamiento interno (ver [arquitectura](arquitectura.md#almacenamiento)),
la base de datos y el set `personal`, y comprueba que encuentra el intérprete de CHIRP.
`where` muestra el almacenamiento, la base de datos, la carpeta de salida actual y el
intérprete de CHIRP en uso.

## 2. Registrar modelos

Descarga la imagen del radio con CHIRP (*Radio → Download*), guárdala y regístrala:

```bash
radiosync radios register --template /path/to/download.img
radiosync radios list
radiosync radios inspect --radio <radio-id>
```

- El id se deriva de fabricante y modelo (`baofeng-uv-5r-mini`); `--radio <id>` lo fija.
- La imagen se copia como template con su SHA-256 y una firma de capacidades del driver.
- Todos los radios del mismo modelo reciben la misma imagen; no hay perfiles por unidad.
- `register` llena los valores por canal del driver (`extras`) y los niveles de potencia.
- `--replace` cambia el template de un modelo ya registrado y respalda el anterior.
- `inspect` avisa si una actualización de CHIRP cambió las capacidades del driver; en ese
  caso, registra de nuevo con `--replace`.

## 3. Importar memorias

```bash
radiosync channels import /path/to/channels.csv --set personal --dry-run
radiosync channels import /path/to/channels.csv --set personal
radiosync channels import /path/to/radio.img --set scanner
radiosync channels import /path/to/catalog.json
```

- CSV e imágenes se leen con los drivers de CHIRP.
- Una programación idéntica (misma RX, duplex/offset o TX, modo y tonos activos) se
  reutiliza: no se duplica. Si nombre o comentario difieren, se conserva el existente y se
  reporta la diferencia.
- La misma frecuencia con otro tono, offset o modo es una memoria distinta.
- El archivo completo se rechaza si tiene columnas desconocidas, `Location` repetidos,
  filas sin frecuencia o memorias D-STAR.
- La potencia de CSV e imágenes no se importa: la decide cada radio (ver
  [potencia](#7-potencia)).
- `--dry-run` muestra el resultado sin guardar.

## 4. Crear y editar memorias

```bash
radiosync channels add --freq 146.520 --name CALL --set personal
radiosync channels add --freq 147.000 --duplex + --offset 0.6 --tmode TSQL --ctone 100.0 --name RPT-ABC
radiosync channels add -i
radiosync channels edit <id> --tmode DTCS --dtcs 023
radiosync channels list --set personal
radiosync channels show <id>
radiosync channels delete <id> [--force]
```

- Frecuencias y offsets en MHz; tonos en Hz; potencia en watts; paso en kHz.
- `--duplex`: `simplex`, `+`, `-`, `split` (TX en `--tx-freq`) u `off` (solo RX).
- CHIRP valida los valores; un tono no estándar se acepta en el catálogo, pero el build lo
  rechaza en los modelos que no lo soportan.
- Editar una memoria cambia todos los sets que la usan.
- `delete` se niega si la memoria está en algún set; `--force` la quita de ellos.

## 5. Sets y presets

Un set es una lista ordenada de memorias. Una memoria puede estar en varios sets sin
duplicarse en el catálogo.

```bash
radiosync sets create scanner --description "Escucha"
radiosync sets add scanner <id> <id> [--position N]
radiosync sets move scanner <id> <posición>
radiosync sets member scanner <id> --alias CORTO --skip S
radiosync sets member scanner <id> --clear-alias --clear-skip
radiosync sets remove scanner <id>
radiosync sets show scanner
radiosync sets list
radiosync sets delete scanner --yes
```

- `--alias` y `--skip` aplican solo dentro de ese set.
- `sets remove` y `sets delete` no borran memorias del catálogo.

Un preset guarda una combinación de sets y, opcionalmente, de modelos:

```bash
radiosync presets create diario --sets personal,repetidoras [--radios <id>,<id>]
radiosync presets list
radiosync build --preset diario
```

## 6. Generar imágenes

```bash
radiosync build                                  # todos los modelos habilitados, sus default_sets
radiosync build --radio <radio-id>               # uno o varios modelos (--radio repetible)
radiosync build --sets personal,scanner          # combinación de sets
radiosync build --output /path/to/output         # otra carpeta de salida
radiosync build --dry-run -v                     # valida y muestra adaptaciones sin publicar
```

Composición de los canales:

- `personal` va primero; el resto en el orden indicado.
- Una memoria aparece una sola vez, en el primer set que la trae; su alias/skip gana.
- La numeración empieza en la primera posición del modelo (0 o 1, según el driver).
- Si los canales no caben en el modelo, el build falla; nunca se recortan.

Salida:

- `<radio-id>_<YYYYMMDD>_<hash8>.img` y `<radio-id>_<YYYYMMDD>_<hash8>.manifest.json`,
  directamente en la carpeta actual o en `--output`, sin subcarpetas.
- `hash8` son los primeros 8 caracteres del SHA-256 de la imagen. Sets, potencia y orden
  quedan en el [manifiesto](formatos.md#manifiesto).
- Si la imagen y sus detalles ya existen, se reutilizan sin reescribirlos; cualquier otra
  coincidencia de nombre añade `_2`, `_3`, ... Nunca se sobrescribe un archivo.
- Si cualquier modelo del lote falla, no se publica ninguno.

## 7. Potencia

La potencia la define cada radio, no el canal:

1. `--power low|mid|high`: todos los canales al nivel que el perfil asigna a ese nombre.
2. Canal con potencia propia (por ejemplo FRS/PMR/GMRS, donde la fija el estándar): el
   nivel del radio más cercano en watts.
3. Canal sin potencia: el nivel `power.default` del perfil.

```bash
radiosync build --power low
radiosync channels export --sets personal --power low --radio <radio-id>
```

## 8. Orden por frecuencia

```bash
radiosync build --sort
radiosync channels export --sets personal,repetidoras --sort --output channels.csv
```

`--sort` ordena por frecuencia RX después de eliminar duplicados. Canales con la misma RX
pero distinta programación conservan su orden relativo. Sin `--sort`, el orden es por
sets. El catálogo y los sets no cambian.

## 9. Nombres y comentarios

**Nombres.** El catálogo guarda el nombre completo; al generar (y al exportar CSV con
`--radio`) cada nombre se adapta al modelo:

1. Mayúsculas si el modelo solo las admite; caracteres no válidos se convierten en separador.
2. Si tiene un número, lo conserva al final y antepone las palabras completas que quepan
   (`REP-ABC-123` → `ABC123`); si ninguna cabe, la más cercana comprimida
   (`NOAA-WX1` → `NWX1`).
3. Sin número, quita palabras vacías (de, la, el, y, ...) y vocales de la última palabra
   a la primera (`Cerro Alto` → `CrrAlt`), y recorta si aún no cabe.
4. Si dos canales distintos terminan con el mismo nombre, el final se numera (2, 3, ...).

Los cambios aparecen como adaptación `name_fit` en `build -v` y en el manifiesto.
`name_fit: false` en el perfil desactiva el acortado.

**Comentarios.** En imágenes y CSV generados el comentario empieza con todos los sets de
la memoria y después conserva el original:

```text
Sets: repetidoras, repetidoras-ref | Comentario original
```

El catálogo no se modifica. En radios sin comentarios nativos, CHIRP guarda el
comentario en la metadata de la imagen (visible en CHIRP, no en la pantalla del radio).

## 10. Validar antes de cargar

```bash
radiosync validate                                   # último build de cada modelo en la carpeta actual
radiosync validate --radio <radio-id>
radiosync validate --output /path/to/output
radiosync validate --manifest /path/to/output/<archivo>.manifest.json
```

Comprueba tamaño y SHA-256 contra el manifiesto y vuelve a abrir la imagen con CHIRP para
comparar cada memoria, memoria especial y setting con lo esperado. No cargues una imagen
que falle. Después, en CHIRP: *File → Open* la imagen y *Radio → Upload*.

## 11. Settings del radio

```bash
radiosync settings export --radio <radio-id> -o settings.json
radiosync settings diff --radio <radio-id> --from /path/to/changed.img
radiosync settings import --radio <radio-id> --from /path/to/changed.img [--dry-run]
```

Flujo: cambia un setting en CHIRP, guarda la imagen y ejecuta `settings import`. El perfil
queda con las diferencias de esa imagen contra el template; el siguiente build las
aplica. También puedes editar `settings` en el perfil (ver [formatos](formatos.md#perfil-de-radio)).

## 12. Exportar y respaldar

```bash
radiosync channels export --sets personal                       # CSV con nombre automático
radiosync channels export --sets personal --output personal.csv
radiosync channels export --sets personal --radio <radio-id>    # nombres adaptados al modelo
radiosync db export                                             # catálogo completo en JSON
radiosync db import catalog.json [--dry-run]
radiosync db backup
```

- Sin `--output`, el archivo se crea en la carpeta actual con sets y fecha en el nombre.
- Si el archivo de destino existe, se respalda antes de sobrescribirlo.
- Cada comando que escribe en la base hace antes una copia consistente en `bkp/` del
  almacenamiento.
