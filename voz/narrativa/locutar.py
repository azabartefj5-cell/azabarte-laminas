#!/usr/bin/env python3
"""Locuta la edición narrativa de azabarte.com con la voz de Google (Gemini TTS).

Lee textos.json (lo produce extraer_textos.mjs a partir de la web publicada) y, para cada pista
cuyo texto haya cambiado desde la última grabación, pide a Gemini la locución bloque a bloque
(título, entradilla, títulos de sección y párrafos), une los bloques con pausas, guarda un MP3 y
anota en audio.json el instante en que empieza cada bloque. El reproductor de la web usa esas
«marcas» para resaltar el párrafo que se está oyendo y desplazar la página con la lectura, igual
que hace con la voz del navegador.

Motores:
  gemini      API de Gemini de Google (variable GEMINI_API_KEY). Modelo gemini-3.8-flash-tts.
  openrouter  El mismo modelo a través de OpenRouter (variable OPENROUTER_API_KEY).
  prueba      Sin red ni clave: genera un tono por bloque con la duración estimada. Solo sirve
              para probar la cadena completa y el reproductor.

Uso típico:
  python locutar.py --motor gemini                 # locuta lo que falte o haya cambiado
  python locutar.py --motor gemini --solo cap:sabemos
  python locutar.py --fijar-base https://cdn.jsdelivr.net/gh/USUARIO/azabarte-laminas@COMMIT/voz/narrativa

El resultado (mp3/*.mp3 y audio.json) sigue el esquema D.audio de la web (datos/censo/audio.json):
  {"base": "...", "voz": {...}, "pistas": {"cap:sabemos": {"src": "mp3/cap-sabemos.mp3",
   "huella": "<sha256 del texto>", "marcas": [0.3, 2.9, ...], "dur": 512.4}}}

Códigos de salida: 0 bien (también si se acabó la cuota del día: se sigue otro día); 1 alguna pista
ha fallado; 2 error que impide seguir (clave, modelo, crédito); 3 los textos no son la edición narrativa.
"""
from __future__ import annotations

import argparse
import array
import base64
import datetime as _dt
import faulthandler
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RATE = 24000  # Gemini TTS entrega PCM de 16 bits, mono, 24 kHz

MODELO = "gemini-3.8-flash-tts"
VOZ = "Charon"  # voz prediseñada de Google: grave, informativa; estable en el tiempo
KBPS = 64

# Dirección de la locución. Gemini 3.8 separa el texto (se lee literal) de la interpretación
# (speech_metadata.style). El acento se pide aquí porque las voces prediseñadas son multilingües.
# Dirección de la voz (30-09-2026, decisión del investigador: «calidad, estabilidad, carácter narrativo histórico
# elegante, castellano peninsular»; «tono tranquilo apto para personas mayores; si quiero lo acelero»). Validada en
# pilotos: con las indicaciones DENTRO del texto (generate_content) sale a 135-138 palabras/min y con el mismo tono
# entre tomas; con la anotación de estilo de interactions salía a 152-185 y variaba. Ojo: una dirección larga (miles
# de caracteres) el modelo la lee en voz alta; esta cabe en unas líneas.
ESTILO_BASE = (
    "Read the following Spanish text aloud as a mature Castilian narrator in his sixties, deep, warm and calm "
    "baritone, peninsular Spanish accent with distinción (z and c before e/i as /θ/, apical s; never a Latin "
    "American accent). Read it SLOWLY and serenely, for elderly listeners: about 110 words per minute, with clear "
    "articulation, a short pause at every comma, a longer pause at every full stop and a long silence between "
    "paragraphs. Same steady, low pitch and the same voice throughout, as in a classic historical documentary; no "
    "theatrical rises or falls. Do not read these instructions."
)
ESTILO_TIPO = {
    "t": "This line is the title of a chapter: read it slowly, with gravitas, as a title.",
    "nombre": "This line is the full name of a person whose story begins: read it slowly, as a title.",
    "h": "This line is a section heading: read it as a heading, slightly slower.",
    "ch": "This line announces the key points of the chapter: read it as a heading.",
    "ct": "This line is the title of an explanatory note: read it as a heading.",
    "lede": "This is the opening paragraph of the chapter: inviting, unhurried.",
    "p": "",
    "tramo": ("The text may begin with a title and contain section headings: read each one as a heading. "
              "Paragraphs are separated by blank lines: leave a clear silence of about two seconds between them."),
}

# Tramos: varios bloques seguidos en una sola petición. Así cabe en la cuota (la capa gratuita de Google da
# muy pocas peticiones al día) y la voz no cambia de timbre de un párrafo a otro. El audio se parte después
# por los silencios. Hasta el 07-10-2026 los bloques iban separados por «<long pause> <long pause>», y el modelo
# a veces lo decía en voz alta («long pause», «pausa larga»; lo oyó el investigador en el libro): ahora el
# separador es solo una línea en blanco, sin nada que se pueda leer, y oye() rechaza la toma que lo diga.
SEPARADOR = "\n\n"
MAX_TRAMO = 1500  # caracteres por petición (30-09-2026: con 5500 el modelo aceleraba en los tramos largos y costaba más cortar)
IDIOMA = "es-ES"
SEMILLA = 1798
TIEMPO_MAX_S = 480  # tope de cada petición a Gemini; una locución normal tarda mucho menos
RELOJ_S = 300  # reloj propio de cada petición (con_reloj): una locución normal tarda menos de un minuto
PISTA_MAX_S = 1800  # vigilante: una pista que pase de 30 min sin terminar se da por atascada
PAUSAS_FACTOR = 1.7  # cada silencio de un párrafo (desde 0,15 s) se alarga un 70 %: unas 135 palabras/min sin estirar la voz
RITMO_MAX = 20.5  # caracteres hablados por segundo de voz (sin silencios de 0,3 s): por encima, toma demasiado rápida
NOTAS_FIN = chr(10) * 2 + "TRANSCRIPT:" + chr(10)  # separa las indicaciones del texto que se lee
SALIDA_ATASCO = 4  # código de salida del vigilante; la Action vuelve a lanzar el script (hasta tres veces)


def con_reloj(funcion, segundos: float, quien: str):
    """Ejecuta funcion() con un reloj propio (29-09-2026). El tiempo máximo del SDK mide la espera entre datos, no
    la petición entera: con la conexión viva, o si la biblioteca espera a que el servidor cierre la tarea, no salta,
    y tres ejecuciones se quedaron horas paradas al empezar una pista. Aquí la llamada corre en un hilo aparte
    y, si no vuelve a tiempo, se abandona (hilo daemon) y se lanza TimeoutError, que locuta_bloque reintenta."""
    res = {}

    def corre():
        try:
            res["ok"] = funcion()
        except BaseException as e:  # noqa: BLE001
            res["error"] = e

    hilo = threading.Thread(target=corre, daemon=True)
    hilo.start()
    hilo.join(segundos)
    if hilo.is_alive():
        raise TimeoutError(f"{quien} no respondió en {int(segundos)} s; se abandona la petición y se reintenta")
    if "error" in res:
        raise res["error"]
    return res.get("ok")


class Vigia:
    """Vigilante de pistas (29-09-2026). Dos ejecuciones de pago se quedaron horas paradas al empezar una pista
    (pj:P108 a las 15:53 y pj:P134 a las 18:20 UTC), la segunda ya con el tope de 8 min por petición: el atasco
    no está (solo) en la espera de la respuesta. Si una pista pasa de PISTA_MAX_S, se vuelca la pila de todos
    los hilos al registro (para ver dónde estaba parada) y se sale con SALIDA_ATASCO. Lo terminado ya está en
    audio.json y en la caché de bloques; la Action relanza el script y sigue con lo pendiente."""

    def __init__(self, segundos: float):
        self.segundos = segundos
        self.t = None

    def arma(self, clave: str) -> None:
        self.desarma()
        def salta():
            log(f"VIGILANTE: la pista {clave} lleva más de {int(self.segundos // 60)} min sin terminar; "
                "se para esta ejecución (lo terminado ya está guardado). Pila de todos los hilos:")
            try:
                faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
            except Exception:  # noqa: BLE001
                pass
            sys.stdout.flush(); sys.stderr.flush()
            os._exit(SALIDA_ATASCO)
        self.t = threading.Timer(self.segundos, salta)
        self.t.daemon = True
        self.t.start()

    def desarma(self) -> None:
        if self.t:
            self.t.cancel()
            self.t = None

# Pausas (segundos) entre bloques, según el tipo del bloque anterior y del siguiente.
INICIO, FINAL = 0.35, 0.9


def pausa(prev: str, sig: str) -> float:
    # Desde el 29-09-2026 también se leen los textos intercalados de los capítulos: «ch» (rótulo de las
    # claves), «cl» (cada clave), «pull» (frase destacada), «ct»/«cp» (título y texto de un recuadro),
    # «li» (lista) y «pie» (nota de una fotografía). Los rótulos llevan pausa de epígrafe, y las notas,
    # algo más de aire que un párrafo, para que se oiga que se sale del hilo y se vuelve a él.
    if prev in ("t", "nombre"):
        return 1.0
    if sig in ("h", "ch", "ct"):
        return 1.1
    if prev in ("h", "ch", "ct"):
        return 0.7
    if prev == "lede":
        return 0.85
    if sig in ("pull", "pie") or prev in ("pull", "cp", "pie"):
        return 0.85
    return 0.55


def log(*a):
    print(*a, flush=True)


class CuotaAgotada(Exception):
    """La API ha agotado la cuota: se para limpiamente y se reanuda en la próxima ejecución."""


class ErrorFatal(Exception):
    """Clave inválida, modelo inexistente, sin crédito: no se arregla reintentando."""


class ErrorBloque(Exception):
    """Un bloque no se ha podido locutar bien: su pista queda pendiente y se sigue con la siguiente."""


# ---------------------------------------------------------------- audio en memoria

def pcm_de(datos: bytes) -> array.array:
    """Muestras int16 mono a 24 kHz a partir de WAV (RIFF) o PCM crudo.

    El WAV se lee a mano: los WAV de una respuesta en streaming pueden declarar tamaño 0 en el
    trozo «data», y entonces el resto del búfer es el audio."""
    if datos[:4] == b"RIFF" and datos[8:12] == b"WAVE":
        pos, canales, bits, frec, crudo = 12, 1, 16, RATE, None
        while pos + 8 <= len(datos):
            ident, tam = datos[pos:pos + 4], struct.unpack("<I", datos[pos + 4:pos + 8])[0]
            cuerpo = pos + 8
            if ident == b"fmt ":
                _fmt, canales, frec = struct.unpack("<HHI", datos[cuerpo:cuerpo + 8])
                bits = struct.unpack("<H", datos[cuerpo + 14:cuerpo + 16])[0]
            elif ident == b"data":
                fin = len(datos) if tam == 0 or cuerpo + tam > len(datos) else cuerpo + tam
                crudo = datos[cuerpo:fin]
                break
            pos = cuerpo + tam + (tam & 1)
        if crudo is None:
            raise ValueError("WAV sin trozo de datos")
        if bits != 16:
            raise ValueError(f"WAV de {bits} bits no admitido")
    else:
        crudo, canales, frec = datos, 1, RATE
    a = array.array("h")
    a.frombytes(crudo[: len(crudo) - (len(crudo) % 2)])
    if canales > 1:
        a = array.array("h", a[::canales])
    if frec != RATE:
        a = remuestrea(a, frec, RATE)
    if not len(a):
        raise ValueError("audio vacío")
    return a


def remuestrea(a: array.array, de: int, a_: int) -> array.array:
    n = int(len(a) * a_ / de)
    out = array.array("h", [0]) * n
    for i in range(n):
        x = i * de / a_
        j = int(x)
        f = x - j
        v0 = a[j] if j < len(a) else 0
        v1 = a[j + 1] if j + 1 < len(a) else v0
        out[i] = int(v0 + (v1 - v0) * f)
    return out


def silencio(seg: float) -> array.array:
    return array.array("h", [0]) * int(round(seg * RATE))


def recorta(a: array.array, umbral: int = 220, margen: float = 0.04) -> array.array:
    """Quita el silencio de los extremos para controlar las pausas entre bloques."""
    n = len(a)
    ini = 0
    while ini < n and abs(a[ini]) < umbral:
        ini += 1
    fin = n - 1
    while fin > ini and abs(a[fin]) < umbral:
        fin -= 1
    if ini >= fin:
        return array.array("h")
    m = int(margen * RATE)
    return a[max(0, ini - m): min(n, fin + m + 1)]


def normaliza(a: array.array, rms_obj_db: float = -20.0, pico_db: float = -1.0) -> array.array:
    """Ganancia única para toda la pista: RMS de la voz a -20 dBFS sin pasar de -1 dBFS de pico."""
    voz = [x for x in a if abs(x) > 300]
    if not voz:
        return a
    rms = math.sqrt(sum(x * x for x in voz) / len(voz)) / 32768.0
    pico = max(abs(x) for x in voz) / 32768.0
    g = (10 ** (rms_obj_db / 20)) / max(rms, 1e-9)
    g = min(g, (10 ** (pico_db / 20)) / max(pico, 1e-9))
    if abs(g - 1) < 0.02:
        return a
    return array.array("h", (max(-32768, min(32767, int(x * g))) for x in a))


def ffmpeg_bin() -> str:
    b = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
    if b:
        return b
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover
        raise ErrorFatal("No hay ffmpeg: instálelo o `pip install imageio-ffmpeg`") from e


def a_mp3(a: array.array, destino: Path, titulo: str, comentario: str, kbps: int = KBPS) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp.mp3")
    cmd = [
        ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "pipe:0",
        "-c:a", "libmp3lame", "-b:a", f"{kbps}k", "-ar", str(RATE), "-ac", "1",
        "-metadata", f"title={titulo}", "-metadata", "artist=Proyecto Origen Azabarte",
        "-metadata", f"comment={comentario}", "-id3v2_version", "3",
        str(tmp),
    ]
    subprocess.run(cmd, input=a.tobytes(), check=True)
    tmp.replace(destino)


# ---------------------------------------------------------------- comprobación de duración

_NUM = {1: 5, 2: 10, 3: 18, 4: 28}


def largo_hablado(texto: str) -> int:
    """Longitud aproximada de lo que se dice: «1798» se lee «mil setecientos noventa y ocho»."""
    t = re.sub(r"\d+", lambda m: "x" * _NUM.get(len(m.group()), 7 * len(m.group())), texto)
    t = re.sub(r"\b[IVXLC]{2,}\b", lambda m: "x" * 10, t)  # siglos en romanos: «XVI» → «dieciséis»
    return len(t)


def duracion_razonable(texto: str, a: array.array):
    dur = len(a) / RATE
    est = largo_hablado(texto)
    cps = est / dur if dur > 0 else 999.0
    lo, hi = (4.0, 30.0) if est < 60 else (8.0, 26.0)
    return dur, cps, lo <= cps <= hi


# ---------------------------------------------------------------- motores de voz

def estilo_de(k: str) -> str:
    extra = ESTILO_TIPO.get(k, "")
    return ESTILO_BASE + ("\n" + extra if extra else "")


class Motor:
    nombre = "?"

    def __init__(self, args):
        self.args = args
        self.cerrojo = threading.Lock()
        self.ultima = 0.0
        self.peticiones = 0
        self.caracteres = 0

    def espera_turno(self):
        rpm = self.args.rpm
        if not rpm or rpm <= 0:
            return
        with self.cerrojo:
            turno = max(time.time(), self.ultima + 60.0 / rpm)
            self.ultima = turno
        falta = turno - time.time()
        if falta > 0:
            time.sleep(falta)

    def cuenta(self, texto):
        with self.cerrojo:
            self.peticiones += 1
            self.caracteres += len(texto)

    def locuta(self, texto: str, k: str) -> array.array:
        raise NotImplementedError


def clasifica(codigo, mensaje: str) -> str:
    """dia | minuto | fatal | bloque | reintentar"""
    m = mensaje.lower()
    if codigo == 429 or "resource_exhausted" in m or "rate limit" in m or "too many requests" in m:
        if any(x in m for x in ("per_day", "perday", "per day", "daily")):
            return "dia"
        return "minuto"
    if codigo in (401, 403) or "api_key_invalid" in m or "api key not valid" in m or "permission_denied" in m:
        return "fatal"
    if codigo == 402 or ("insufficient" in m and "credit" in m):
        return "fatal"
    if codigo == 404 or ("model" in m and "not found" in m):
        return "fatal"
    if codigo == 400:
        return "bloque"
    return "reintentar"


def retraso_sugerido(mensaje: str):
    m = re.search(r"retry(?:Delay)?\W+(?:in\s+)?(\d+(?:\.\d+)?)\s*s", mensaje, re.I)
    return float(m.group(1)) if m else None


class MotorGemini(Motor):
    nombre = "gemini"

    def __init__(self, args):
        super().__init__(args)
        # Varias claves, alternándolas (30-09-2026, orden del investigador: «úsalas todas las gratuitas alternándolas»):
        # GEMINI_API_KEY y GEMINI_API_KEY_2…_9. Cada petición va con la siguiente; la que agota su cuota del día se
        # aparta y siguen las demás. Con una sola clave, todo es como antes.
        claves = []
        for nombre in ["GEMINI_API_KEY", "GOOGLE_API_KEY"] + [f"GEMINI_API_KEY_{i}" for i in range(2, 10)]:
            v = (os.environ.get(nombre) or "").strip()
            if v and v not in claves:
                claves.append(v)
        if not claves:
            raise ErrorFatal("Falta la variable GEMINI_API_KEY")
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        # Tiempo máximo por petición (29-09-2026). Sin él, una petición colgada no fallaba nunca: la ejecución
        # de pago 36591271235 se quedó más de dos horas y media en «Locutar lo pendiente» cuando el lote debía
        # tardar unos 50 minutos (diagnóstico de la sesión «Navegación en versión narrativa»). Con el tope, la
        # petición falla y locuta_bloque la reintenta como cualquier otro fallo. Comprobado que el SDK lo aplica
        # a interactions.create (en milisegundos).
        # Sin reintentos del SDK (29-09-2026, causa de los atascos, vista en la pila que volcó el vigilante): el
        # «retries=None» que se pasaba a create() el SDK no lo admite, así que se repetía la llamada sin él y
        # quedaban sus reintentos por defecto, que respetan el Retry-After de Google y dormían horas en
        # _gaos/utils/retries.py sin decir nada. Con attempts=0 el error (429, 5xx…) llega al momento a
        # locuta_bloque, que sabe si esperar un minuto o parar hasta mañana y lo deja en el registro.
        self.types = types
        self.intentos = {}
        opciones = types.HttpOptions(timeout=TIEMPO_MAX_S * 1000, retry_options=types.HttpRetryOptions(attempts=0))
        self.clientes = [genai.Client(api_key=c, http_options=opciones) for c in claves]
        self.client = self.clientes[0]
        self.agotadas, self.turno_cliente = set(), 0
        if len(self.clientes) > 1:
            log(f"{len(self.clientes)} claves de Google, alternándolas")

    def _cliente(self):
        """Siguiente clave con cuota, por turno (a prueba de hilos): (índice, cliente) o (None, None)."""
        with self.cerrojo:
            libres = [i for i in range(len(self.clientes)) if i not in self.agotadas]
            if not libres:
                return None, None
            i = libres[self.turno_cliente % len(libres)]
            self.turno_cliente += 1
            return i, self.clientes[i]

    def _pide(self, **peticion):
        """Pide con la siguiente clave. Si esa clave está en su límite (del día o del minuto), prueba las demás; si
        todas lo están, devuelve el último error, que locuta_bloque clasifica (esperar o parar hasta mañana)."""
        ultimo = None
        for _ in range(len(self.clientes)):
            i, cli = self._cliente()
            if cli is None:
                break
            try:
                return con_reloj(lambda c=cli: c.models.generate_content(**peticion), RELOJ_S, "Gemini")
            except Exception as e:  # noqa: BLE001
                tipo = clasifica(*self.error(e))
                if len(self.clientes) == 1 or tipo not in ("dia", "minuto"):
                    raise
                if tipo == "dia":
                    with self.cerrojo:
                        if i not in self.agotadas:
                            self.agotadas.add(i)
                            log(f"  clave {i + 1} de {len(self.clientes)}: cuota del día agotada; sigo con las demás")
                ultimo = e
        if ultimo is not None:
            raise ultimo
        raise CuotaAgotada("todas las claves tienen agotada la cuota del día")

    def locuta(self, texto, k):
        self.espera_turno()
        # Semilla distinta en cada reintento del mismo texto: con la misma, Gemini repite la misma toma fallida.
        clave_t = hashlib.sha1((k + "|" + texto).encode("utf-8")).hexdigest()
        with self.cerrojo:
            n = self.intentos.get(clave_t, 0)
            self.intentos[clave_t] = n + 1
        semilla = None if self.args.semilla is None else self.args.semilla + n
        cfg = self.types.GenerateContentConfig(
            response_modalities=["AUDIO"], seed=semilla,
            speech_config=self.types.SpeechConfig(
                language_code=self.args.idioma or None,
                voice_config=self.types.VoiceConfig(
                    prebuilt_voice_config=self.types.PrebuiltVoiceConfig(voice_name=self.args.voz))))
        contenido = estilo_de(k) + NOTAS_FIN + texto
        # Los reintentos los gobierna locuta_bloque; el SDK no reintenta (retry_options attempts=0 en el cliente).
        r = self._pide(model=self.args.modelo, contents=contenido, config=cfg)
        self.cuenta(texto)
        cand = (getattr(r, "candidates", None) or [None])[0]
        fin = str(getattr(cand, "finish_reason", "") or "").upper()
        if cand is None or ("MAX_TOKENS" in fin or "SAFETY" in fin or "OTHER" in fin):
            raise ErrorBloque(f"Gemini cortó la respuesta ({fin or 'sin candidato'})")
        partes = getattr(getattr(cand, "content", None), "parts", None) or []
        datos = next((p.inline_data.data for p in partes if getattr(p, "inline_data", None)), None)
        if not datos:
            raise RuntimeError("La respuesta de Gemini no trae audio")
        if isinstance(datos, str):
            datos = base64.b64decode(datos)
        return pcm_de(bytes(datos))

    def config(self):
        voz = {"voice": self.args.voz}
        if self.args.idioma:
            voz["language"] = self.args.idioma
        gc = {"speech_config": [voz]}
        if self.args.semilla is not None:
            gc["seed"] = self.args.semilla
        return gc

    @staticmethod
    def error(e):
        return getattr(e, "status_code", None) or getattr(e, "code", None), str(e)


class MotorOpenRouter(Motor):
    nombre = "openrouter"
    URL = "https://openrouter.ai/api/v1/audio/speech"

    def __init__(self, args):
        super().__init__(args)
        self.clave = os.environ.get("OPENROUTER_API_KEY")
        if not self.clave:
            raise ErrorFatal("Falta la variable OPENROUTER_API_KEY")

    def locuta(self, texto, k):
        self.espera_turno()
        modelo = self.args.modelo if "/" in self.args.modelo else "google/" + self.args.modelo
        meta = {"speech_metadata": {"style": estilo_de(k)}}
        cuerpo = {"model": modelo, "input": texto, "voice": self.args.voz, "response_format": "pcm",
                  "provider": {"options": {"google-ai-studio": meta, "google-vertex": meta}}}
        req = urllib.request.Request(
            self.URL, data=json.dumps(cuerpo).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self.clave}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://azabarte.com", "X-Title": "Proyecto Origen Azabarte"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                tipo = r.headers.get("Content-Type", "")
                datos = r.read()
        except urllib.error.HTTPError as e:
            texto_err = e.read().decode("utf-8", "replace")[:600]
            # Si OpenRouter rechaza la dirección de estilo no se sigue sin ella: sin estilo no hay acento
            # castellano garantizado, y esa grabación no se volvería a hacer.
            if e.code == 400 and "Provider returned error" not in texto_err and (
                    "ZodError" in texto_err or "Unrecognized key" in texto_err or "provider.options" in texto_err):
                raise ErrorFatal("OpenRouter no admite la dirección de estilo (acento): use GEMINI_API_KEY. "
                                 + texto_err) from e
            raise RuntimeError(f"HTTP {e.code}: {texto_err}") from e
        if "json" in tipo:
            raise RuntimeError(f"HTTP 200 sin audio: {datos.decode('utf-8', 'replace')[:400]}")
        self.cuenta(texto)
        return pcm_de(datos)

    @staticmethod
    def error(e):
        m = re.search(r"HTTP (\d{3})", str(e))
        return (int(m.group(1)) if m else None), str(e)


class MotorPrueba(Motor):
    """Tono suave con la duración de una lectura real (≈ 15 caracteres por segundo)."""

    nombre = "prueba"

    @staticmethod
    def tono(seg, f):
        n = int(seg * RATE)
        out = array.array("h", [0]) * n
        for i in range(n):
            env = min(1.0, i / 2400, (n - i) / 2400)
            out[i] = int(2500 * env * math.sin(2 * math.pi * f * i / RATE))
        return out

    def locuta(self, texto, k):
        out = array.array("h")
        for j, bloque in enumerate(texto.split(SEPARADOR)):
            if j:
                out.extend(silencio(2.4))
            frases = [x for x in re.split(r"(?<=[.;:?!])\s+", bloque) if x] or [bloque]
            for i, fr in enumerate(frases):
                if i:  # pausas de frase de 0,3 a 1,1 s, como las de la voz real
                    out.extend(silencio(0.3 + 0.8 * ((len(fr) * 7919) % 100) / 100))
                out.extend(self.tono(max(0.5, largo_hablado(fr) / 15.0), 220.0 if k == "p" else 330.0))
        self.cuenta(texto)
        return out

    @staticmethod
    def error(e):
        return None, str(e)


MOTORES = {"gemini": MotorGemini, "openrouter": MotorOpenRouter, "prueba": MotorPrueba}


# ---------------------------------------------------------------- caché por bloque

class Cache:
    def __init__(self, carpeta: Path, firma: str):
        self.dir = carpeta
        self.firma = firma
        self.dir.mkdir(parents=True, exist_ok=True)

    def ruta(self, texto, k):
        h = hashlib.sha1(f"{self.firma}\n{k}\n{texto}".encode("utf-8")).hexdigest()
        return self.dir / f"{h}.pcm"

    def lee(self, texto, k):
        p = self.ruta(texto, k)
        if p.exists():
            a = array.array("h")
            a.frombytes(p.read_bytes())
            if len(a):
                return a
        return None

    def guarda(self, texto, k, a):
        p = self.ruta(texto, k)
        tmp = p.with_name(p.name + f".{threading.get_ident()}.tmp")
        tmp.write_bytes(a.tobytes())
        os.replace(tmp, p)

    def olvida(self, claves):
        for texto, k in claves:
            p = self.ruta(texto, k)
            p.unlink(missing_ok=True)
            for ext in (".pcm", ".txt"):  # tampoco se aprovechan las tomas descartadas: se pide de nuevo
                (self.dir / "rechazos" / (p.stem + ext)).unlink(missing_ok=True)

    def guarda_rechazo(self, texto, k, a, motivo):
        """Aparta una toma que no pasó la validación, con el motivo: cuesta una petición de la cuota y así
        se puede escuchar y revisar después en lugar de perderla."""
        d = self.dir / "rechazos"
        d.mkdir(parents=True, exist_ok=True)
        base = d / self.ruta(texto, k).stem
        base.with_suffix(".pcm").write_bytes(a.tobytes())
        base.with_suffix(".txt").write_text(" ".join(motivo.split()) + f"\n\n{texto}\n", "utf-8")

    def recupera_rechazo(self, texto, k, valida):
        """Si hay una toma descartada de este mismo texto que la validación de ahora acepta (p. ej. porque
        se descartó por un corte entre párrafos que ya se elige mejor), pasa a la caché y ahorra la petición."""
        base = self.dir / "rechazos" / self.ruta(texto, k).stem
        p = base.with_suffix(".pcm")
        if not p.exists():
            return None
        a = array.array("h")
        a.frombytes(p.read_bytes())
        if not len(a) or not valida(a)[2]:
            return None
        self.guarda(texto, k, a)
        p.unlink(missing_ok=True)
        base.with_suffix(".txt").unlink(missing_ok=True)
        return a

    def limpia(self, dias=21):
        """Borra lo que lleve semanas sin usarse (restos de tramos partidos o de textos que cambiaron)."""
        limite = time.time() - dias * 86400
        for p in [*self.dir.glob("*.pcm"), *self.dir.glob("rechazos/*")]:
            try:
                if p.stat().st_mtime < limite:
                    p.unlink()
            except OSError:
                pass


def valida_bloque(texto):
    """Un bloque suelto vale si dura lo que corresponde a su texto y no dice nada que no esté en él."""
    def valida(a):
        valida.motivo = ""
        dur, cps, ok = duracion_razonable(texto, a)
        if ok:
            malas, claro = oye(a, texto)
            if malas:
                ok, valida.motivo = False, "dice en voz alta: " + ", ".join(malas[:4])
            elif claro is not None and len(_palabras(texto)) >= 25 and claro < INTELIGIBLE_MIN:
                ok, valida.motivo = False, f"se entiende mal (toma borrosa o con otro acento: {claro:.0%} del texto)"
        if ok:
            d = distincion(a, texto)
            if d and d[1] >= 6 and d[0] / d[1] < DISTINCION_MIN:
                ok, valida.motivo = False, f"acento sin distinción c/z (seseo: {d[0]} θ de {d[1]})"
        return dur, cps, ok
    return valida


def locuta_bloque(motor: Motor, cache: Cache, texto: str, k: str, intentos: int = 4,
                  esperas_max: int = 10, valida=None, ultimo_recurso: bool = True) -> array.array:
    guardado = cache.lee(texto, k)
    if guardado is not None:
        return guardado
    if valida is not None:
        guardado = cache.recupera_rechazo(texto, k, valida)
        if guardado is not None:
            log(f"  se aprovecha una toma descartada antes que ahora sí vale: «{' '.join(texto[:40].split())}…»")
            return guardado
    fallos, esperas, espera = 0, 0, 20.0
    mejor, ultimo = None, ""
    while fallos < intentos:
        try:
            a = recorta(motor.locuta(texto, k))
        except (ErrorFatal, CuotaAgotada):
            raise
        except ErrorBloque as e:
            ultimo = str(e)
            fallos += 1
            if not ultimo_recurso:
                break
            continue
        except Exception as e:  # noqa: BLE001
            codigo, msg = motor.error(e)
            tipo = clasifica(codigo, msg)
            ultimo = f"{codigo}: {msg[:240]}"
            if tipo == "dia":
                raise CuotaAgotada(msg[:300]) from e
            if tipo == "fatal":
                raise ErrorFatal(msg[:500]) from e
            if tipo == "minuto":
                # Las esperas por límite de peticiones no gastan intentos.
                esperas += 1
                if esperas > esperas_max:
                    raise CuotaAgotada("el límite de peticiones no cede: " + msg[:200]) from e
                t = min(max(retraso_sugerido(msg) or espera, 5.0), 180.0)
                log(f"  límite de peticiones; espero {int(t)} s")
                time.sleep(t)
                espera = min(espera * 1.6, 120.0)
                continue
            fallos += 1
            log(f"  error ({codigo}) en «{texto[:40]}…»: {msg[:160]}")
            if tipo == "bloque" and fallos >= 2:
                break
            time.sleep(min(5 * fallos, 30))
            continue
        valida = valida or valida_bloque(texto)
        dur, cps, ok = valida(a)
        if ok:
            cache.guarda(texto, k, a)
            return a
        fallos += 1
        motivo = getattr(valida, "motivo", "")
        dice = motivo.startswith("dice en voz alta") or "seseo" in motivo or "se entiende mal" in motivo
        ultimo = (f"toma rechazada: {dur:.1f} s para «{texto[:40]}…» ({cps:.1f} c/s)" if dice else
                  f"duración sospechosa: {dur:.1f} s para «{texto[:40]}…» ({cps:.1f} c/s)")
        if motivo:
            ultimo += f"; {motivo}"
        if not ultimo_recurso:
            try:
                cache.guarda_rechazo(texto, k, a, ultimo)
            except OSError:
                pass
        log("  " + ultimo + "; repito")
        # Solo vale como último recurso una toma con voz y ritmo verosímil, nunca un silencio ni una que diga lo que
        # no está en el texto.
        if not dice and dur >= 0.3 and 3.0 <= cps <= 40.0 and (mejor is None or abs(cps - 15) < abs(mejor[1] - 15)):
            mejor = (a, cps)
    if mejor is not None and ultimo_recurso:
        log(f"  se acepta la mejor toma ({mejor[1]:.1f} c/s) de «{texto[:40]}…»")
        cache.guarda(texto, k, mejor[0])
        return mejor[0]
    raise ErrorBloque(ultimo or "sin audio")


# ---------------------------------------------------------------- tramos

def tramos(bloques, maximo):
    """Índices de bloques agrupados en tramos de hasta `maximo` caracteres hablados; si el tramo ya va
    mediado, se corta con preferencia antes de un título de sección."""
    out, cur, n = [], [], 0
    for i, b in enumerate(bloques):
        largo = largo_hablado(b["x"])
        if cur and (n + largo > maximo or (b["k"] == "h" and n > 0.55 * maximo)):
            out.append(cur)
            cur, n = [], 0
        cur.append(i)
        n += largo
    if cur:
        out.append(cur)
    return out


TRAMA = 0.02


def energia(a):
    f = int(TRAMA * RATE)
    return [math.sqrt(sum(x * x for x in a[i:i + f]) / f) for i in range(0, len(a) - f + 1, f)]


def silencios(rms, minimo=0.25):
    """Silencios internos (inicio, fin) en segundos, con umbral relativo al nivel de la voz."""
    if not rms:
        return []
    nivel = sorted(rms)[int(0.9 * (len(rms) - 1))]
    umbral = max(120.0, nivel * 0.08)
    out, ini = [], None
    for i, r in enumerate(rms):
        if r < umbral:
            if ini is None:
                ini = i
        else:
            if ini is not None and ini > 0 and (i - ini) * TRAMA >= minimo:
                out.append((ini * TRAMA, i * TRAMA))
            ini = None
    return out


def alarga_pausas(a: array.array, factor: float = None, minimo: float = 0.15) -> array.array:
    """Alarga cada silencio interno (de al menos `minimo` s) en (factor - 1) de su duración, metiendo silencio en su
    centro (30-09-2026). Da una lectura más tranquila sin estirar la voz, que es lo que la distorsiona."""
    factor = PAUSAS_FACTOR if factor is None else factor
    if factor <= 1.0 or len(a) == 0:
        return a
    out, pos = array.array("h"), 0
    for ini, fin in silencios(energia(a), minimo=minimo):
        i0, i1 = int(ini * RATE), int(fin * RATE)
        medio = (i0 + i1) // 2
        out.extend(a[pos:medio])
        out.extend(array.array("h", [0]) * int((i1 - i0) * (factor - 1)))
        pos = medio
    out.extend(a[pos:])
    return out


def ritmo_habla(a: array.array, texto: str) -> float:
    """Caracteres hablados por segundo de voz, sin contar silencios de 0,3 s o más."""
    dur = len(a) / RATE
    pausas = sum(fin - ini for ini, fin in silencios(energia(a), minimo=0.3))
    return largo_hablado(texto) / max(0.1, dur - pausas)


# ---------------------------------------------------------------- oído (07-10-2026)
# El investigador oyó en el libro tomas que decían «long pause» o «pausa larga» y otras con una respiración larga
# antes del párrafo. La duración no lo delata (un segundo de más en un párrafo largo cae dentro del ritmo normal):
# hace falta oír. oye() transcribe la toma con faster-whisper: se rechaza si dice palabras de la dirección que no están
# en el texto o si se entiende mal (tomas borrosas o con otro acento, que también oyó: Whisper casa entonces pocas
# palabras con el texto); quita_respiraciones() deja en silencio las respiraciones aisladas.

INTELIGIBLE_MIN = 0.70  # parte del texto que Whisper (base) entiende: en el libro publicado, de 0,84 a 0,99 (mediana 0,94)
INTRUSAS = ("paus", "pauz", "long", "llarg", "silenc", "transcri", "instrucc", "instruct", "narrat", "spanish", "slowly")
_OIDO = {"modelo": None, "cerrojo": threading.Lock(), "aviso": False}


def _palabras(s: str):
    s = s.lower().translate(str.maketrans("áéíóúüàèìòùï", "aeiouuaeioui"))
    return re.findall(r"[a-zñ]+", s)


def inteligible(oidas, texto_palabras) -> float:
    """Parte de las palabras del texto (sin cifras, que Whisper escribe a su modo) que se oyen y en su orden."""
    import difflib
    t = [w for w in texto_palabras if not w.isdigit()]
    if not t:
        return 1.0
    sm = difflib.SequenceMatcher(None, [w for w in oidas if not w.isdigit()], t, autojunk=False)
    return sum(m.size for m in sm.get_matching_blocks()) / len(t)


def oye(a: array.array, texto: str):
    """(intrusas, inteligibilidad): palabras de la dirección («pausa», «long», «silencio»…) que se oyen en la toma y no
    están en el texto, y la parte del texto que se entiende (de 0 a 1). ([], None) si no hay faster-whisper (entonces
    avisa una vez y no frena nada)."""
    if os.environ.get("VOZ_OIDO", "1") == "0":
        return [], None
    with _OIDO["cerrojo"]:
        if _OIDO["modelo"] is None:
            try:
                from faster_whisper import WhisperModel  # type: ignore
                _OIDO["modelo"] = WhisperModel(os.environ.get("VOZ_OIDO_MODELO") or "base", device="cpu",
                                               compute_type="int8")
            except Exception as e:  # noqa: BLE001
                if not _OIDO["aviso"]:
                    log(f"  aviso: sin faster-whisper no se oyen las tomas ({str(e)[:120]})")
                    _OIDO["aviso"] = True
                return [], None
        import numpy as np  # viene con faster-whisper
        x = np.frombuffer(a.tobytes(), dtype=np.int16).astype(np.float32) / 32768.0
        x = np.interp(np.arange(0, len(x), RATE / 16000), np.arange(len(x)), x)  # Whisper oye a 16 kHz
        segs, _ = _OIDO["modelo"].transcribe(x.astype(np.float32), language="es", beam_size=1, vad_filter=True,
                                            condition_on_previous_text=False)
        oido = " ".join(s.text for s in segs)
    en_texto = {}
    for w in _palabras(texto):
        en_texto[w] = en_texto.get(w, 0) + 1
    vistas, malas = {}, []
    oidas = _palabras(oido)
    for w in oidas:
        vistas[w] = vistas.get(w, 0) + 1
        if any(w.startswith(p) for p in INTRUSAS) and vistas[w] > en_texto.get(w, 0):
            malas.append(w)
    return malas, inteligible(oidas, _palabras(texto))


# Acento (07-10-2026). El investigador oyó tomas con acento latino. Con distinción, cada z y cada c ante e/i suena
# θ; con seseo, s. Un reconocedor de fonemas (wav2vec2 xlsr-53 espeak, que transcribe en AFI) cuenta las θ de la
# toma; se comparan con las que pide el texto. Medido en el libro publicado: con distinción salen entre 0,8 y 1,2
# por cada z o ce/ci del texto; una toma que sesea da casi cero. Por debajo de DISTINCION_MIN, se rechaza.
FONEMAS_MODELO = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
DISTINCION_MIN = 0.45
_FON = {"m": None, "cerrojo": threading.Lock(), "aviso": False}


def zetas_del_texto(texto: str) -> int:
    t = texto.lower().translate(str.maketrans("áéíóúü", "aeiouu"))
    return len(re.findall(r"z|c(?=[eiy])", t))


def distincion(a: array.array, texto: str):
    """(θ oídas, θ que pide el texto), o None si no hay reconocedor de fonemas (avisa una vez y no frena nada)."""
    if os.environ.get("VOZ_ACENTO", "1") == "0":
        return None
    esperadas = zetas_del_texto(texto)
    with _FON["cerrojo"]:
        if _FON["m"] is None:
            try:
                import torch  # type: ignore
                from huggingface_hub import hf_hub_download  # type: ignore
                from transformers import Wav2Vec2ForCTC  # type: ignore
                torch.set_num_threads(max(1, (os.cpu_count() or 2)))
                modelo = Wav2Vec2ForCTC.from_pretrained(FONEMAS_MODELO).eval()
                vocab = json.loads(Path(hf_hub_download(FONEMAS_MODELO, "vocab.json")).read_text("utf-8"))
                _FON["m"] = (torch, modelo, {v for k, v in vocab.items() if k.startswith("θ")})
            except Exception as e:  # noqa: BLE001
                if not _FON["aviso"]:
                    log(f"  aviso: sin reconocedor de fonemas no se comprueba el acento ({str(e)[:120]})")
                    _FON["aviso"] = True
                return None
        import numpy as np
        torch, modelo, theta = _FON["m"]
        x = np.frombuffer(a.tobytes(), dtype=np.int16).astype(np.float32) / 32768.0
        x = np.interp(np.arange(0, len(x), RATE / 16000), np.arange(len(x)), x).astype(np.float32)
        oidas = 0
        for k in range(0, len(x), 16000 * 10):  # trozos de 10 s: poca memoria
            t = x[k:k + 16000 * 10]
            if len(t) < 1600:
                continue
            t = (t - t.mean()) / (t.std() + 1e-7)
            with torch.no_grad():
                ids = modelo(torch.from_numpy(t)[None]).logits[0].argmax(-1).tolist()
            oidas += sum(1 for j, i in enumerate(ids) if i in theta and (j == 0 or ids[j - 1] != i))
    return oidas, esperadas


def quita_respiraciones(a: array.array) -> array.array:
    """Silencia las respiraciones (07-10-2026). La voz de Gemini a veces toma aire, largo y audible, antes de un
    párrafo. En la pista son islas de ruido suave entre silencios: sin voz (todo por debajo de la voz en 22 dB o más)
    y separadas de ella por al menos 60 ms de silencio. También la toma de aire pegada al comienzo de una frase, si
    dura 0,3 s o más, es ruido (espectro plano) y queda 28 dB por debajo de la voz. La duración no cambia: las
    marcas siguen valiendo. Las colas de las palabras van pegadas a la voz y no se tocan."""
    import numpy as np
    fr = int(TRAMA * RATE)
    x = np.frombuffer(a.tobytes(), dtype=np.int16).astype(np.float32)
    n = len(x) // fr
    if n < 10:
        return a
    tr = x[: n * fr].reshape(n, fr)
    d = 20 * np.log10(np.sqrt((tr ** 2).mean(1)) + 1e-3)
    nivel = float(np.percentile(d, 90))
    sp = np.abs(np.fft.rfft(tr * np.hanning(fr), axis=1)) ** 2 + 1e-9
    plano = np.exp(np.log(sp).mean(1)) / sp.mean(1)
    sil = d < nivel - 60
    fuera = np.zeros(n, dtype=bool)
    i, islas, quitado = 0, 0, 0.0
    while i < n:
        if sil[i]:
            i += 1
            continue
        j, hueco = i, 0
        while j < n and hueco < 3:
            hueco = hueco + 1 if sil[j] else 0
            j += 1
        fin = j - hueco
        if d[i:fin].max() < nivel - 22:  # isla sin voz: respiración o ruido
            fuera[i:fin] = True
            islas += 1
            quitado += (fin - i) * TRAMA
        else:  # toma de aire pegada al comienzo de la frase
            k = i
            while k < fin and d[k] < nivel - 28:
                k += 1
            if (k - i) * TRAMA >= 0.3 and plano[i:k].mean() >= 0.05:
                fuera[i:k - 1] = True
                islas += 1
                quitado += (k - 1 - i) * TRAMA
        i = j
    if not islas:
        return a
    g = np.repeat((~fuera).astype(np.float32), fr)
    w = fr // 2  # rampas de 10 ms, sin chasquidos (media móvil por suma acumulada)
    c = np.concatenate(([0.0], np.cumsum(np.pad(g, (w // 2, w - w // 2 - 1), mode="edge"), dtype=np.float64)))
    g = ((c[w:] - c[:-w]) / w).astype(np.float32)
    y = x.copy()
    y[: n * fr] *= g
    log(f"  respiraciones silenciadas: {islas} ({quitado:.1f} s)")
    return array.array("h", np.clip(np.round(y), -32768, 32767).astype(np.int16).tobytes())


def cambia_tempo(a: array.array, factor: float) -> array.array:
    """Cambia la velocidad sin cambiar el tono (atempo de ffmpeg). factor < 1 = más lento."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-f", "s16le", "-ar", str(RATE), "-ac", "1",
           "-i", "pipe:0", "-filter:a", f"atempo={factor:.4f}", "-f", "s16le", "-ar", str(RATE), "-ac", "1",
           "pipe:1"]
    return array.array("h", subprocess.run(cmd, input=a.tobytes(), capture_output=True, check=True).stdout)


def elige_cortes(sil, esperados, dur):
    """Elige, en orden, un silencio por cada frontera entre bloques. Premia los silencios largos y penaliza
    que cada trozo se aparte de la duración que le toca por su texto (y, poco, que la frontera se aleje de su
    posición absoluta prevista): así una deriva acumulada del ritmo no arrastra varias fronteras a pausas de
    frase. En los trozos cortos (títulos y epígrafes) cuenta además la desviación relativa: que un título de
    2 s quede en 0,8 s o en 5 s apenas mueve la cuenta en segundos, pero es un corte en la coma del propio
    título o una frase del párrafo siguiente. En los párrafos largos ese término se desvanece, para no
    forzar un ritmo igual en todos cuando la voz se toma su tiempo en alguno. Cada trozo debe durar al
    menos un tercio de lo previsto."""
    m, ns = len(esperados), len(sil)
    if m == 0:
        return []
    if ns < m:
        return None
    ANCLA, TROZO = 0.015, 0.04  # segundos de silencio que «cuesta» cada segundo de desviación
    REL, CORTO = 0.5, 4.0  # peso de la desviación relativa, pleno en trozos de hasta CORTO segundos
    centro = [(a + b) / 2 for a, b in sil]
    largo = [b - a for a, b in sil]

    def pena(seg, esp):
        rel = abs(math.log(max(seg, 0.05) / max(esp, 0.05)))
        return TROZO * abs(seg - esp) + REL * min(1.0, CORTO / max(esp, 0.05)) * rel
    NADA = float("-inf")
    dp = [[NADA] * ns for _ in range(m)]
    antes = [[-1] * ns for _ in range(m)]
    for k in range(m):
        esp = esperados[k] - (esperados[k - 1] if k else 0.0)
        for j in range(ns):
            base = largo[j] - ANCLA * abs(centro[j] - esperados[k])
            if k == 0:
                if centro[j] >= esp / 3:
                    dp[0][j] = base - pena(centro[j], esp)
                continue
            mejor, arg = NADA, -1
            for i in range(j):
                if dp[k - 1][i] == NADA:
                    continue
                seg = centro[j] - centro[i]
                if seg < esp / 3:
                    continue
                v = dp[k - 1][i] - pena(seg, esp)
                if v > mejor:
                    mejor, arg = v, i
            if arg >= 0:
                dp[k][j] = mejor + base
                antes[k][j] = arg
    ultimo_esp = dur - esperados[-1]
    finales = [j for j in range(ns) if dp[m - 1][j] > NADA and dur - centro[j] >= ultimo_esp / 3]
    if not finales:
        return None
    j = max(finales, key=lambda x: dp[m - 1][x] - pena(dur - centro[x], ultimo_esp))
    elegidos = [j]
    for k in range(m - 1, 0, -1):
        j = antes[k][j]
        elegidos.append(j)
    return [sil[i] for i in reversed(elegidos)]


def parte_tramo(a: array.array, textos):
    """Parte el audio de un tramo en los audios de sus bloques. Solo se corta dentro de silencios (o, si
    faltan, en el punto de menos energía cercano), así un corte dudoso nunca parte una palabra: como mucho
    mueve el resaltado una frase. Devuelve (trozos, exacto, silencios_de_corte)."""
    n = len(textos)
    if n == 1:
        return [a], True, []
    dur = len(a) / RATE
    rms = energia(a)
    sil = silencios(rms)
    PAUSA = 30  # la pausa larga entre párrafos, en «caracteres» de lectura
    largos_txt = [largo_hablado(x) for x in textos]
    total, acc, esperados = sum(largos_txt) + PAUSA * (n - 1), 0, []
    for w in largos_txt[:-1]:
        acc += w + PAUSA
        esperados.append(dur * (acc - PAUSA / 2) / total)
    cortes = elige_cortes(sil, esperados, dur)
    if cortes is None:
        cortes = []
        for e in esperados:  # sin silencios bastantes: el tramo de menos energía a ±1,5 s
            c = int(e / TRAMA)
            v = range(max(1, c - 75), min(len(rms) - 1, c + 75))
            i = min(v, key=lambda x: rms[x]) if len(v) else c
            cortes.append((i * TRAMA, (i + 1) * TRAMA))
        exacto = False
    else:
        # Exacto si los cortes son justo los silencios más largos y se distinguen con holgura del resto.
        largos = sorted((b - a_ for a_, b in sil), reverse=True)
        elegidos = sorted(b - a_ for a_, b in cortes)
        exacto = len(largos) >= n - 1 and elegidos[0] >= largos[n - 2] - 1e-9 and (
            len(largos) == n - 1 or elegidos[0] - largos[n - 1] >= 0.35)
    trozos, ini = [], 0
    for c0, c1 in cortes:
        medio = int((c0 + c1) / 2 * RATE)
        trozos.append(recorta(a[ini:medio]))
        ini = medio
    trozos.append(recorta(a[ini:]))
    return trozos, exacto, cortes


def valida_tramo(textos):
    """Un tramo vale si su ritmo global es de lectura normal, no pasa del tope de salida y cada párrafo, una
    vez partido, dura lo que corresponde a su texto (un párrafo saltado o un final cortado no pasan)."""
    habla = sum(largo_hablado(x) for x in textos)

    def valida(a):
        valida.motivo = ""
        dur = len(a) / RATE
        pausas = sum(b - a_ for a_, b in silencios(energia(a), minimo=1.2))
        voz = max(0.1, dur - pausas)
        cps = habla / voz
        ok = (8.0 <= cps <= 20.0) if habla >= 200 else (4.0 <= cps <= 30.0)
        if not ok:
            valida.motivo = f"ritmo global {cps:.1f} c/s"
        elif dur > 8 * 60:
            ok, valida.motivo = False, f"dura {dur:.0f} s, más del tope de salida"
        if ok:
            trozos, _e, _c = parte_tramo(a, textos)
            ritmos = [duracion_razonable(x, tr) if len(tr) else (0.0, 999.0, False)
                      for x, tr in zip(textos, trozos)]
            malos = [i for i, r in enumerate(ritmos) if not r[2]]
            # Un final cortado deja el último párrafo «demasiado rápido»: ahí el tope es más estricto.
            if not malos and largo_hablado(textos[-1]) >= 60 and ritmos[-1][1] > 21.0:
                malos = [len(textos) - 1]
            if malos:
                ok = False
                valida.motivo = "párrafos fuera de ritmo: " + ", ".join(
                    f"{i + 1}/{len(textos)} «{textos[i][:30]}…» {ritmos[i][0]:.1f} s, {ritmos[i][1]:.1f} c/s"
                    for i in malos[:3])
        if ok:  # solo se oye la toma que ya ha pasado lo demás: así cuesta poco
            malas, claro = oye(a, " ".join(textos))
            if malas:
                ok, valida.motivo = False, "dice en voz alta palabras que no están en el texto: " + ", ".join(malas[:4])
            elif claro is not None and claro < INTELIGIBLE_MIN:
                ok, valida.motivo = False, f"se entiende mal (toma borrosa o con otro acento: {claro:.0%} del texto)"
            elif claro is not None:
                log(f"  se entiende el {claro:.0%} del texto")
        if ok:
            d = distincion(a, " ".join(textos))
            if d and d[1] >= 6 and d[0] / d[1] < DISTINCION_MIN:
                ok, valida.motivo = False, f"acento sin distinción c/z (seseo: {d[0]} θ de {d[1]})"
            elif d and d[1] >= 6:
                log(f"  distinción c/z: {d[0]} θ de {d[1]}")
        return dur, cps, ok
    return valida


def mitad(bloques):
    """Índice que parte los bloques en dos mitades de lectura parecida."""
    largos = [largo_hablado(b["x"]) for b in bloques]
    total, acc, mejor, h = sum(largos), 0, None, 1
    for i in range(1, len(bloques)):
        acc += largos[i - 1]
        d = abs(acc - total / 2)
        if mejor is None or d < mejor:
            mejor, h = d, i
    return h


def locuta_tramo(motor, cache, bloques, partido=False):
    if len(bloques) == 1:
        b = bloques[0]
        return [locuta_bloque(motor, cache, b["x"], b["k"])], True
    textos = [b["x"] for b in bloques]
    try:
        # Una sola petición: repetir el mismo texto con la misma semilla daría lo mismo.
        a = locuta_bloque(motor, cache, SEPARADOR.join(textos), "tramo", intentos=1,
                          valida=valida_tramo(textos), ultimo_recurso=False)
    except ErrorBloque as e:
        if partido:  # ya era una mitad: la pista queda pendiente para otro día, sin gastar más cuota
            raise
        h = mitad(bloques)
        log(f"  tramo de {len(bloques)} bloques no válido ({str(e)[:120]}); se pide en dos mitades")
        t1, e1 = locuta_tramo(motor, cache, bloques[:h], partido=True)
        t2, e2 = locuta_tramo(motor, cache, bloques[h:], partido=True)
        return t1 + t2, e1 and e2
    trozos, exacto, _ = parte_tramo(a, textos)
    return trozos, exacto


def grupos_de(bloques, args):
    return tramos(bloques, args.max_tramo) if args.modo == "tramos" else [[i] for i in range(len(bloques))]


def claves_cache(t, args):
    """Claves de caché que usa una pista con su agrupación normal (sin contar mitades de tramos fallidos)."""
    bl, out = t["bloques"], []
    for g in grupos_de(bl, args):
        if len(g) == 1:
            out.append((bl[g[0]]["x"], bl[g[0]]["k"]))
        else:
            out.append((SEPARADOR.join(bl[i]["x"] for i in g), "tramo"))
    return out


# ---------------------------------------------------------------- manifiesto

def nombre_mp3(clave: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", clave) + ".mp3"


def lee_json(p: Path, defecto):
    if p.exists():
        return json.loads(p.read_text("utf-8"))
    return defecto


def escribe_json(p: Path, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", "utf-8")
    tmp.replace(p)


def firma_voz(args) -> str:
    base = f"{args.modelo}|{args.voz}|{hashlib.sha1(ESTILO_BASE.encode()).hexdigest()[:10]}"
    if args.modo == "tramos":
        base += f"|tramos{args.max_tramo}"
    if args.motor != "openrouter" and (args.idioma or args.semilla is not None):
        base += f"|{args.idioma}|{args.semilla}"
    return "prueba|" + base if args.motor == "prueba" else base


def hecha(man, salida: Path, t, firma) -> bool:
    ya = man["pistas"].get(t["clave"])
    return bool(ya and ya.get("huella") == t["huella"] and ya.get("firma") == firma
                and ya.get("src") and (salida / ya["src"]).exists())


def locuta_pista(motor, cache, t, args):
    bl = t["bloques"]
    grupos = grupos_de(bl, args)
    audios, errores, aproximadas = [None] * len(bl), [], []
    with ThreadPoolExecutor(max_workers=max(1, args.hilos)) as ex:
        futuros = [ex.submit(locuta_tramo, motor, cache, [bl[i] for i in g]) for g in grupos]
        for g, f in zip(grupos, futuros):
            try:
                trozos, exacto = f.result()
                for i, tr in zip(g, trozos):
                    audios[i] = tr
                if not exacto:
                    aproximadas.append(f"{g[0] + 1}-{g[-1] + 1}")
            except Exception as e:  # noqa: BLE001
                errores.append(e)
    if errores:
        for tipo in (ErrorFatal, CuotaAgotada):
            for e in errores:
                if isinstance(e, tipo):
                    raise e
        raise errores[0]
    if aproximadas:
        log(f"  aviso: marcas aproximadas en los bloques {', '.join(aproximadas)} (cortes dudosos entre párrafos)")
    log(f"  {len(grupos)} peticiones para {len(bl)} bloques")
    audios = [alarga_pausas(x) for x in audios]
    piezas, marcas = [silencio(INICIO)], []
    pos = len(piezas[0])
    for i, b in enumerate(t["bloques"]):
        if i > 0:
            s = silencio(pausa(t["bloques"][i - 1]["k"], b["k"]))
            piezas.append(s)
            pos += len(s)
        marcas.append(round(pos / RATE, 2))
        piezas.append(audios[i])
        pos += len(audios[i])
    piezas.append(silencio(FINAL))
    pista = array.array("h")
    for p in piezas:
        pista.extend(p)
    # Tope de velocidad (30-09-2026): si la pista entera va más deprisa de RITMO_MAX, se frena, pero nunca más de
    # un 5 % (frenar distorsiona más que acelerar). Las lentas se dejan: el oyente puede acelerar en la web.
    r = ritmo_habla(pista, " ".join(b["x"] for b in t["bloques"]))
    if r > RITMO_MAX:
        f = max(0.95, RITMO_MAX / r)
        pista = cambia_tempo(pista, f)
        marcas = [round(x / f, 2) for x in marcas]
        log(f"  ritmo {r:.1f} c/s de habla: se frena al {f * 100:.0f} %")
    else:
        log(f"  ritmo {r:.1f} c/s de habla")
    return normaliza(quita_respiraciones(pista)), marcas


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--motor", choices=sorted(MOTORES), default="gemini")
    ap.add_argument("--modelo", default=os.environ.get("VOZ_MODELO") or MODELO)
    ap.add_argument("--voz", default=os.environ.get("VOZ_NOMBRE") or None,
                    help=f"voz de Google; si no se indica, la del manifiesto actual o {VOZ}")
    ap.add_argument("--textos", default=str(AQUI / "textos.json"))
    ap.add_argument("--salida", default=str(AQUI))
    ap.add_argument("--solo", default="", help="claves separadas por comas (cap:sabemos,pj:P001)")
    ap.add_argument("--max-pistas", type=int, default=0, help="0 = sin límite")
    ap.add_argument("--rpm", type=float, default=float(os.environ.get("VOZ_RPM") or 0),
                    help="peticiones por minuto como máximo (0 = sin pausa entre peticiones)")
    ap.add_argument("--hilos", type=int, default=int(os.environ.get("VOZ_HILOS") or 4),
                    help="peticiones a la vez (1 = de una en una)")
    ap.add_argument("--modo", choices=["tramos", "bloques"], default=os.environ.get("VOZ_MODO") or "tramos",
                    help="tramos: varios párrafos por petición (menos cuota, voz continua); bloques: uno a uno")
    ap.add_argument("--max-tramo", type=int, default=os.environ.get("VOZ_MAX_TRAMO") or MAX_TRAMO,
                    help="caracteres hablados por petición en modo tramos")
    ap.add_argument("--idioma", default=os.environ.get("VOZ_IDIOMA") or IDIOMA,
                    help="idioma de la voz para Gemini (es-ES)")
    ap.add_argument("--semilla", default=os.environ.get("VOZ_SEMILLA") or str(SEMILLA),
                    help="semilla de generación para Gemini; 'no' para no fijarla")
    ap.add_argument("--limite-minutos", type=float, default=0,
                    help="no empieza pistas nuevas pasado este tiempo (0 = sin límite)")
    ap.add_argument("--forzar", action="store_true", help="regenera aunque la huella coincida")
    ap.add_argument("--cache", default=str(AQUI / ".cache"))
    ap.add_argument("--fijar-base", default=None, help="solo reescribe la base de audio.json y sale")
    ap.add_argument("--podar", action="store_true",
                    help="borra las pistas que ya no existen en la web (con freno si serían muchas)")
    ap.add_argument("--forzar-poda", action="store_true", help="poda aunque desaparezcan muchas pistas")
    args = ap.parse_args(argv)
    if args.modo not in ("tramos", "bloques"):
        ap.error(f"--modo / VOZ_MODO debe ser tramos o bloques, no {args.modo!r}")
    try:
        args.semilla = None if str(args.semilla).lower() in ("", "no", "none") else int(args.semilla)
    except ValueError:
        ap.error(f"--semilla / VOZ_SEMILLA debe ser un número o 'no', no {args.semilla!r}")

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    man_p = salida / "audio.json"
    man = lee_json(man_p, {"esquema": "4.6", "base": "", "voz": {}, "pistas": {}})
    man.setdefault("pistas", {})
    man.setdefault("voz", {})

    if args.fijar_base is not None:
        # Base por pista (29-09-2026): cada MP3 conserva la dirección del commit en que se publicó, y solo las
        # pistas recién locutadas (sin «base» propia) reciben la nueva. Así la dirección de lo que no cambia no
        # se mueve y jsDelivr la sigue teniendo en caché: con una base única, cada publicación enfriaba todos
        # los audios y el primer oyente esperaba segundos (hasta 41 s medidos) a que jsDelivr los trajera.
        nueva = args.fijar_base.rstrip("/")
        n = 0
        for p in (man.get("pistas") or {}).values():
            if isinstance(p, dict) and not p.get("base"):
                p["base"] = nueva
                n += 1
        man["base"] = nueva
        escribe_json(man_p, man)
        log(f"base = {nueva} · {n} pistas nuevas con ella; las demás conservan la suya")
        return 0

    textos = lee_json(Path(args.textos), None)
    if not textos:
        raise SystemExit(f"No existe {args.textos}; ejecute antes extraer_textos.mjs")
    pistas = textos.get("pistas") or []
    if textos.get("edicion") != "narrativa" or not any(t["clave"].startswith("cap:") for t in pistas):
        log(f"ERROR: {args.textos} no es la edición narrativa (edición «{textos.get('edicion')}», "
            f"{len(pistas)} pistas). No se locuta ni se borra nada.")
        return 3
    vivas = {t["clave"] for t in pistas}

    # La voz se mantiene entre ejecuciones: la indicada, o la del manifiesto, o la de siempre.
    args.voz = args.voz or man["voz"].get("voz") or VOZ
    firma = firma_voz(args)
    cache = Cache(Path(args.cache) / re.sub(r"[^A-Za-z0-9]+", "_", firma), firma)
    cache.limpia()

    if args.podar:
        sobran = [c for c in man["pistas"] if c not in vivas]
        tope = max(3, int(0.2 * len(man["pistas"])))
        if len(sobran) > tope and not args.forzar_poda:
            log(f"AVISO: la poda quitaría {len(sobran)} pistas (más de {tope}); no se poda. "
                "Si es correcto, repita con --forzar-poda.")
        else:
            for clave in sobran:
                src = man["pistas"][clave].get("src")
                if src and (salida / src).exists():
                    (salida / src).unlink()
                del man["pistas"][clave]
                log(f"podada {clave}")

    solo = {s.strip() for s in args.solo.split(",") if s.strip()}
    pendientes = []
    for t in pistas:
        if solo and t["clave"] not in solo:
            continue
        if not args.forzar and hecha(man, salida, t, firma):
            cache.olvida(claves_cache(t, args))  # ya está en un MP3 publicado: su caché sobra
            continue
        if args.forzar:
            cache.olvida(claves_cache(t, args))  # forzar es pedir de nuevo, no reutilizar lo guardado
        pendientes.append(t)
    # Primero el libro (30-09-2026, orden del investigador): «Antes de nosotros» solo se lee en el lector y es lo que más se
    # escucha; luego los capítulos de la web y, al final, los relatos de personajes y lo demás. Dentro de cada grupo, el
    # orden de la web (el del libro, capítulo a capítulo). Con cupo escaso, lo más leído suena antes.
    PRIORIDAD = {"lib": 0, "cap": 1, "pj": 2, "bio": 3}
    pendientes.sort(key=lambda t: PRIORIDAD.get(t["clave"].split(":", 1)[0], 9))
    if args.max_pistas > 0:
        pendientes = pendientes[: args.max_pistas]

    total_c = sum(t["chars"] for t in pendientes)
    peticiones = sum(len(tramos(t["bloques"], args.max_tramo)) if args.modo == "tramos" else len(t["bloques"])
                     for t in pendientes)
    log(f"{len(pendientes)} pistas por locutar ({total_c} caracteres, unas {peticiones} peticiones) con "
        f"{args.motor} · {args.modelo} · voz {args.voz} · modo {args.modo}")
    if not pendientes:
        escribe_json(man_p, man)
        return 0

    motor = MOTORES[args.motor](args)
    if not man["voz"] or not solo:
        man["voz"] = {
            "motor": "Google Gemini TTS" + (" (vía OpenRouter)" if args.motor == "openrouter" else ""),
            "modelo": args.modelo,
            "voz": args.voz,
            "aviso": "Locución con voz sintética generada por IA (Google Gemini).",
        }
        if args.motor == "prueba":
            man["voz"].update({"motor": "Prueba (tonos sin voz)", "aviso": "Pista de prueba: tonos sin voz."})

    hechas, fallidas, seguidas = 0, [], 0
    codigo_salida = 0
    inicio = time.time()
    try:
        vigia = Vigia(PISTA_MAX_S)
        for n, t in enumerate(pendientes, 1):
            if args.limite_minutos and time.time() - inicio > args.limite_minutos * 60:
                log(f"Límite de {args.limite_minutos:.0f} min alcanzado; el resto queda para la próxima ejecución.")
                break
            log(f"[{n}/{len(pendientes)}] {t['clave']} · {t['titulo']} · {len(t['bloques'])} bloques, {t['chars']} caracteres")
            vigia.arma(t["clave"])
            try:
                pista, marcas = locuta_pista(motor, cache, t, args)
                src = "mp3/" + nombre_mp3(t["clave"])
                a_mp3(pista, salida / src, t["titulo"], man["voz"].get("aviso", ""))
            except (ErrorFatal, CuotaAgotada):
                raise
            except Exception as e:  # noqa: BLE001
                fallidas.append(t["clave"])
                seguidas += 1
                log(f"  ✗ {t['clave']} queda pendiente: {str(e)[:300]}")
                if seguidas >= 3:
                    log("Tres pistas seguidas han fallado; se para esta ejecución.")
                    break
                continue
            seguidas = 0
            man["pistas"][t["clave"]] = {
                "src": src,
                "huella": t["huella"],
                "marcas": marcas,
                "dur": round(len(pista) / RATE, 2),
                "bytes": (salida / src).stat().st_size,
                "titulo": t["titulo"],
                "firma": firma,
                "generado": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            escribe_json(man_p, man)
            hechas += 1
            log(f"  ✓ {src} · {man['pistas'][t['clave']]['dur']:.0f} s")
    except CuotaAgotada as e:
        log(f"Cuota agotada: {e}")
        log("Se han guardado las pistas terminadas; la próxima ejecución continúa donde se quedó.")
    except ErrorFatal as e:
        log(f"ERROR: {e}")
        codigo_salida = 2
    finally:
        escribe_json(man_p, man)
        log(f"Pistas terminadas en esta ejecución: {hechas}. Fallidas: {len(fallidas)} {fallidas[:10]}. "
            f"Peticiones: {motor.peticiones}. Caracteres enviados: {motor.caracteres}.")
        faltan = [t["clave"] for t in pistas if not hecha(man, salida, t, firma)]
        log(f"Pistas pendientes en total: {len(faltan)} de {len(pistas)}.")
    if codigo_salida == 0 and fallidas:
        codigo_salida = 1
    return codigo_salida


if __name__ == "__main__":
    sys.exit(main())
