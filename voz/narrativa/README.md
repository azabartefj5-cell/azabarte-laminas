# Locución de la edición narrativa con la voz de Google

Grabaciones de la edición narrativa de azabarte.com leídas con **Gemini 3.8 Flash TTS**, el modelo de voz de
Google, para que el botón «Escuchar este capítulo» (y «Escuchar su historia» en cada personaje) suene con una
voz de narrador en lugar de la voz del navegador. El reproductor de la web ya estaba preparado para pistas
pregrabadas: resalta el párrafo que se está oyendo y desplaza la página con la lectura, igual que con la voz
del sistema. Aquí se generan esas pistas y su manifiesto.

| Qué | Dónde |
|---|---|
| Textos que se leen, con su huella | `textos.json` (76 pistas, unos 270 000 caracteres, unas 5 h de audio) |
| Grabaciones | `mp3/*.mp3` (mono, 24 kHz, 64 kbps) |
| Manifiesto que lee la web | `audio.json` (mismo esquema que `D.audio` / `datos/censo/audio.json`) |
| Generación automática | `.github/workflows/voz-narrativa.yml` |

## Cómo se pone en marcha

1. **Añadir la clave de voz como secreto, nunca en un fichero.** El repositorio es público: una clave escrita
   en él quedaría a la vista de cualquiera. En GitHub, en este repositorio: *Settings → Secrets and variables →
   Actions → New repository secret*. Nombre `GEMINI_API_KEY` y como valor la clave de Google AI Studio
   (aistudio.google.com → *Get API key*). Sirve también `OPENROUTER_API_KEY` con una clave de OpenRouter: usa
   el mismo modelo de Google y se paga con el crédito de OpenRouter.
2. **Lanzar la locución.** *Actions → Locutar la edición narrativa → Run workflow*. Si no se lanza a mano, la
   ejecución diaria (9:17 UTC, después de que Google reinicie la cuota) la hace sola y continúa cada día donde
   se quedó.
3. **Aplicar el parche de la web una sola vez** (ver abajo) y desplegar como de costumbre. A partir de ahí las
   grabaciones nuevas o regeneradas aparecen solas, sin volver a desplegar.

**Dos claves (29-09-2026, decisión del investigador).** `GEMINI_API_KEY` es una clave **gratuita** y es la
de siempre: la usan la ejecución diaria, la que lanza `publicar.cmd` tras cada despliegue de la web y las
manuales. `GEMINI_API_KEY_PAGO` es de pago y solo se usa lanzando la Action a mano con «clave: pago»
(`gh workflow run voz-narrativa.yml -f clave=pago`), cuando el investigador lo pida en ese momento. El primer
lote completo se grabó con ella.

**Cuánto tarda.** La capa gratuita de Google da solo 10 peticiones al día a `gemini-3.8-flash-tts`. Por eso el
generador pide varios párrafos seguidos en cada petición («tramos»): la edición completa son unas 106
peticiones, unos 11 días de ejecuciones diarias. Activando la facturación en el proyecto de Google de la clave
(el propio aviso de límite enlaza a ai.dev/rate-limit), el límite sube y todo termina en una sola ejecución.

Coste aproximado con pago por uso, a precios de septiembre de 2026 (Google duplica el precio el 1 de enero de 2027):

| Volumen | Gemini 3.8 Flash TTS |
|---|---|
| Toda la edición narrativa, unos 270 000 caracteres | entre 4 y 6 USD |
| Un capítulo de 7 500 caracteres | entre 0,10 y 0,15 USD |

## Qué hace cada ejecución

1. `extraer_textos.mjs` descarga la página publicada y extrae los textos **con las mismas funciones de la web**
   (bloque `VZ-TEXTO` del módulo `voz.js`): título, entradilla, títulos de sección y párrafos de cada capítulo,
   y nombre, entradilla y relato de cada personaje. Desde el 29-09-2026, también cada capítulo del libro continuo
   «Antes de nosotros» (pistas `lib:<id>`, regla `vzBloquesLibro`). Calcula la huella SHA-256 de cada texto.
2. `locutar.py` locuta solo lo nuevo o lo que ha cambiado (huella distinta). Agrupa los bloques en tramos de
   hasta unos 5 500 caracteres, separados por una pausa larga explícita, y pide cada tramo de una vez: menos
   peticiones y la misma voz de principio a fin, sin cambios de timbre entre párrafos. Después parte el audio
   por los silencios (eligiendo, para cada frontera, el silencio más largo cerca de donde debería caer según el
   texto; nunca corta dentro de la voz). En títulos y epígrafes, que duran uno o dos segundos, pesa además la
   desviación relativa: así no se corta en la coma de un título («Ondategi, la aldea de la pila») ni se mete
   en el epígrafe la primera frase del párrafo siguiente. Después une los bloques con pausas uniformes, iguala el volumen, guarda el MP3
   y anota en `audio.json` el segundo en que empieza cada bloque (`marcas`). Esas marcas son las que mueven el
   resaltado y el desplazamiento de la página. Un tramo solo se acepta si su ritmo es de lectura normal y cada
   párrafo dura lo que le corresponde (así no pasa un párrafo saltado ni un final cortado); si no, se pide una
   vez en dos mitades y, si tampoco sale, la pista queda pendiente para otro día sin gastar más cuota. La toma
   descartada no se tira: queda en la caché (`.cache/rechazos/`) junto al motivo (qué párrafo falló y con qué
   ritmo), para escucharla y revisar el caso. Antes de volver a pedir ese mismo texto, se prueba la toma
   descartada con la validación del momento: si ahora pasa (porque se descartó por un corte que hoy se elige
   mejor), se usa y no se gasta cuota.
3. La Action publica los MP3, clava la dirección del CDN al commit y purga la caché de `audio.json` en jsDelivr.

La web solo usa una grabación si su huella coincide con el texto que muestra. Si se edita un capítulo, ese
capítulo vuelve a sonar con la voz del navegador hasta que la ejecución diaria lo relocute.

## Voz y dirección

**Desde el 30-09-2026: voz culta, tranquila y estable** (decisión del investigador: «calidad, estabilidad, carácter
narrativo histórico elegante, castellano peninsular»; «tono tranquilo apto para personas mayores; si quiero lo
acelero»). Medido sobre las pistas anteriores: 169 palabras/min de media (148-187) y ritmo desigual entre pistas.
Lo que se hizo, validado con pilotos (`tmp/voz_narrativa` y el registro de `CONTROL_INVESTIGACION.md`):

- Las indicaciones van **dentro del texto** (`generate_content`, «Read the following Spanish text aloud as a mature
  Castilian narrator… SLOWLY… for elderly listeners… Do not read these instructions. TRANSCRIPT: …»), no en la
  anotación de estilo de `interactions`: así sale más pausada y con el mismo tono entre tomas. Una dirección larga
  (miles de caracteres) el modelo la **lee en voz alta**: la de `ESTILO_BASE` cabe en unas líneas.
- Tramos de **1.500 caracteres** como mucho (`MAX_TRAMO`): en tramos largos el modelo acelera.
- **Pausas alargadas** en cada párrafo (`PAUSAS_FACTOR` = 1,7 desde silencios de 0,15 s): unas 135 palabras/min sin
  estirar la voz. Si la pista entera pasa de `RITMO_MAX` (20,5 caracteres por segundo de habla), se frena como mucho
  un 5 %; las lentas se dejan (frenar distorsiona más que acelerar, y el oyente acelera en la web).
- Otra semilla en cada reintento del mismo texto (con la misma, Gemini repite la toma fallida).
- Las citas en primera persona de los personajes (otra función, hoy apagada en la web) se harán con la voz
  Algenib y habla de Las Pedroñeras: indicaciones del investigador en `tmp/voz_narrativa/indicaciones_pedronero.md`.

- Voz prediseñada **Charon** (grave, informativa). Es estable en el tiempo: las voces diseñadas a medida caducan.
  Otras candidatas: Orus, Iapetus, Rasalgethi, Sadaltager; femeninas, Gacrux y Sulafat. Se cambia en el campo
  «voz» al lanzar la Action a mano o con la variable de repositorio `VOZ_NOMBRE`. La voz elegida queda anotada
  en `audio.json` y las ejecuciones siguientes la conservan. Cambiarla relocuta todo.
- La dirección (acento castellano peninsular, tono de narrador de documental, ritmo pausado) está en
  `ESTILO_BASE` dentro de `locutar.py`, y además se fija el idioma de la voz a `es-ES` y una semilla de
  generación para que los tramos suenen igual. Cambiar cualquiera de estas cosas relocuta todo.
- Prueba del 28-09-2026 con la clave real, evaluada por Gemini escuchando el audio: acento castellano
  peninsular con distinción c/z, lectura literal al 100 % y naturalidad de 8 a 9,5 sobre 10. Generando párrafo
  a párrafo el timbre variaba entre párrafos; por eso se pasó a tramos.
- Cada bloque se comprueba por su duración, contando los años como palabras: si la voz se come texto o añade
  silencios, se repite, y nunca se publica una toma muda. Un bloque que no sale deja su pista pendiente y se
  sigue con las demás.
- Es voz sintética: el reproductor lo indica («voz sintética (IA)») y cada MP3 lo lleva en sus metadatos.
- Las voces famosas de ElevenReader, como la de Burt Reynolds, son solo para uso personal dentro de su app y no se
  pueden publicar. Por eso se usa una voz de Google con licencia para publicar.

## Ejecutarlo a mano

```bash
pip install -r voz/narrativa/requirements.txt          # google-genai e imageio-ffmpeg
node voz/narrativa/extraer_textos.mjs                   # o --html copia/local/index.html
export GEMINI_API_KEY=...                               # o OPENROUTER_API_KEY y --motor openrouter
python voz/narrativa/locutar.py --motor gemini --solo cap:sabemos   # una pista para escucharla
python voz/narrativa/locutar.py --motor gemini                      # todo lo pendiente
python voz/narrativa/locutar.py --motor prueba --salida /tmp/prueba # sin clave: tonos, para probar
```

Opciones útiles: `--voz`, `--modo tramos|bloques`, `--max-tramo` (caracteres por petición), `--idioma`,
`--semilla`, `--hilos` (peticiones a la vez, 4 por defecto), `--rpm` (tope de peticiones por minuto),
`--forzar`, `--max-pistas`, `--podar` (quita las pistas que ya no están en la web; se frena si serían muchas,
salvo con `--forzar-poda`).

Salvaguardas: el extractor y el generador se niegan a trabajar si la página no es la edición narrativa o llega
sin capítulos. Así un despliegue equivocado de la web no borra las grabaciones. Si la subida falla, la Action
deja el audio generado como artefacto descargable durante 30 días.

## Parche de la web

El reproductor de la web lee hoy `D.audio`, que se incrusta al construir desde `datos/censo/audio.json`. Hay dos
formas de conectarlo con estas grabaciones:

- **Recomendada: `parches/voz-narrativa-gemini.patch`** (o sustituir el módulo por `parches/voz.js`). Hace que
  la web consulte también este `audio.json` al cargar, por jsDelivr, y elija la grabación cuya huella coincida
  con el texto. Así las pistas que genere la Action aparecen sin desplegar. Desde la carpeta de la web:

      patch -p1 < /ruta/a/azabarte-laminas/parches/voz-narrativa-gemini.patch

  El parche está hecho sobre `public/app.js` publicado el 27-09-2026. Si `app.js` se construye a partir de
  `voz.js`, sustituya ese módulo por `parches/voz.js`, que es el módulo completo ya modificado. Después,
  regenerar `index.html` y desplegar como de costumbre.
- **Sin tocar código:** copiar este `audio.json` a `datos/censo/audio.json`, construir y desplegar. Funciona con
  el código actual, pero cada relocución obliga a copiarlo y desplegar otra vez.

Se ha probado en Chromium con la página publicada y pistas de prueba:

- La grabación se elige por huella, y las 76 huellas calculadas por el navegador coinciden con `textos.json`.
- El resaltado sigue al audio.
- «Párrafo siguiente» y la barra saltan a la marca correcta.
- Un texto cambiado vuelve a la voz del navegador.
