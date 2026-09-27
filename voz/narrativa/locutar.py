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
"""
from __future__ import annotations

import argparse
import array
import base64
import datetime as _dt
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request
import wave
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RATE = 24000  # Gemini TTS entrega PCM de 16 bits, mono, 24 kHz

MODELO = "gemini-3.8-flash-tts"
VOZ = "Charon"  # voz prediseñada de Google: grave, informativa; estable en el tiempo
KBPS = 64

# Dirección de la locución. Gemini 3.8 separa el texto (se lee literal) de la interpretación
# (speech_metadata.style). El acento se pide aquí porque las voces prediseñadas son multilingües.
ESTILO_BASE = (
    "AUDIO PROFILE: Documentary and audiobook narrator from Spain reading a family history "
    "about the Azabarte surname (Las Pedroñeras, Cuenca, and Álava).\n"
    "ACCENT: Castilian Spanish from central Spain (Madrid). Peninsular pronunciation with "
    "distinción: 'z' and 'c' before 'e'/'i' pronounced /θ/, 's' apical. Never a Latin American accent.\n"
    "STYLE: Warm, serious and clear. Calm, measured, unhurried pacing with natural pauses at "
    "commas and full stops. Sober and respectful, never theatrical."
)
ESTILO_TIPO = {
    "t": "This line is the title of a chapter: read it slowly, with gravitas, as a title.",
    "nombre": "This line is the full name of a person whose story begins: read it slowly, as a title.",
    "h": "This line is a section heading: read it as a heading, slightly slower.",
    "lede": "This is the opening paragraph of the chapter: inviting, unhurried.",
    "p": "",
}

# Pausas (segundos) entre bloques, según el tipo del bloque anterior y del siguiente.
INICIO, FINAL = 0.35, 0.9


def pausa(prev: str, sig: str) -> float:
    if prev in ("t", "nombre"):
        return 1.0
    if sig == "h":
        return 1.1
    if prev == "h":
        return 0.7
    if prev == "lede":
        return 0.85
    return 0.55


def log(*a):
    print(*a, flush=True)


class CuotaAgotada(Exception):
    """La API ha agotado la cuota del día: se para limpiamente y se reanuda otro día."""


class ErrorFatal(Exception):
    """Clave inválida, modelo inexistente u otro error que no se arregla reintentando."""


# ---------------------------------------------------------------- audio en memoria

def pcm_de(datos: bytes) -> array.array:
    """Devuelve muestras int16 a 24 kHz a partir de WAV (RIFF) o PCM crudo."""
    if datos[:4] == b"RIFF":
        with wave.open(io.BytesIO(datos)) as w:
            ch, sw, fr = w.getnchannels(), w.getsampwidth(), w.getframerate()
            crudo = w.readframes(w.getnframes())
        if sw != 2:
            raise ValueError(f"WAV de {sw * 8} bits no admitido")
        a = array.array("h")
        a.frombytes(crudo)
        if ch > 1:
            a = array.array("h", a[::ch])
        if fr != RATE:
            a = remuestrea(a, fr, RATE)
        return a
    a = array.array("h")
    a.frombytes(datos[: len(datos) - (len(datos) % 2)])
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


def a_mp3(a: array.array, destino: Path, titulo: str, comentario: str) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp.mp3")
    cmd = [
        ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "pipe:0",
        "-c:a", "libmp3lame", "-b:a", f"{KBPS}k", "-ar", str(RATE), "-ac", "1",
        "-metadata", f"title={titulo}", "-metadata", "artist=Proyecto Origen Azabarte",
        "-metadata", f"comment={comentario}", "-id3v2_version", "3",
        str(tmp),
    ]
    subprocess.run(cmd, input=a.tobytes(), check=True)
    tmp.replace(destino)


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

    def locuta(self, texto: str, k: str) -> array.array:
        raise NotImplementedError


def clasifica(codigo, mensaje: str):
    m = mensaje.lower()
    if codigo == 429 or "resource_exhausted" in m or "rate limit" in m:
        if any(x in m for x in ("per_day", "perday", "per day", "daily")):
            return "dia"
        return "minuto"
    if codigo in (401, 403) or "api key not valid" in m or "api_key_invalid" in m or "permission" in m:
        return "fatal"
    if codigo == 404 or "not found" in m and "model" in m:
        return "fatal"
    if codigo == 402 or "insufficient" in m and "credit" in m:
        return "fatal"
    if codigo is None or codigo >= 500 or codigo == 408:
        return "reintentar"
    return "fatal" if codigo == 400 else "reintentar"


class MotorGemini(Motor):
    nombre = "gemini"

    def __init__(self, args):
        super().__init__(args)
        clave = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not clave:
            raise ErrorFatal("Falta la variable GEMINI_API_KEY")
        from google import genai  # type: ignore

        self.client = genai.Client(api_key=clave)

    def locuta(self, texto, k):
        self.espera_turno()
        it = self.client.interactions.create(
            model=self.args.modelo,
            input=[{
                "type": "text",
                "text": texto,
                "annotations": [{"type": "speech_metadata", "style": estilo_de(k)}],
            }],
            response_format={"type": "audio"},
            generation_config={"speech_config": [{"voice": self.args.voz}]},
        )
        au = getattr(it, "output_audio", None)
        if au is None or not getattr(au, "data", None):
            raise RuntimeError("La respuesta de Gemini no trae audio")
        datos = au.data
        if isinstance(datos, str):
            datos = base64.b64decode(datos)
        elif isinstance(datos, (bytes, bytearray)) and datos[:4] != b"RIFF":
            try:
                datos = base64.b64decode(datos, validate=True)
            except Exception:
                pass
        self.peticiones += 1
        self.caracteres += len(texto)
        return pcm_de(bytes(datos))

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
        self.con_estilo = True

    def _pide(self, cuerpo):
        req = urllib.request.Request(
            self.URL, data=json.dumps(cuerpo).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self.clave}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://azabarte.com", "X-Title": "Proyecto Origen Azabarte"})
        with urllib.request.urlopen(req, timeout=300) as r:
            tipo = r.headers.get("Content-Type", "")
            datos = r.read()
        if "json" in tipo:
            raise urllib.error.HTTPError(self.URL, 200, datos.decode("utf-8", "replace")[:500], None, None)
        return datos

    def locuta(self, texto, k):
        self.espera_turno()
        modelo = self.args.modelo if "/" in self.args.modelo else "google/" + self.args.modelo
        cuerpo = {"model": modelo, "input": texto, "voice": self.args.voz, "response_format": "pcm"}
        if self.con_estilo:
            meta = {"speech_metadata": {"style": estilo_de(k)}}
            cuerpo["provider"] = {"options": {"google-ai-studio": meta, "google-vertex": meta}}
        try:
            datos = self._pide(cuerpo)
        except urllib.error.HTTPError as e:
            cuerpo_err = e.read().decode("utf-8", "replace") if hasattr(e, "read") and e.fp else str(e.msg)
            if e.code == 400 and self.con_estilo and ("provider" in cuerpo_err or "option" in cuerpo_err):
                log("  OpenRouter no acepta la dirección de estilo; se sigue sin ella")
                self.con_estilo = False
                return self.locuta(texto, k)
            raise RuntimeError(f"HTTP {e.code}: {cuerpo_err[:400]}") from e
        self.peticiones += 1
        self.caracteres += len(texto)
        return pcm_de(datos)

    @staticmethod
    def error(e):
        m = re.search(r"HTTP (\d{3})", str(e))
        return (int(m.group(1)) if m else None), str(e)


class MotorPrueba(Motor):
    """Tono suave con la duración de una lectura real (≈ 15 caracteres por segundo)."""

    nombre = "prueba"

    def locuta(self, texto, k):
        seg = max(0.6, len(texto) / 15.0)
        n = int(seg * RATE)
        f = 220.0 if k == "p" else 330.0
        out = array.array("h", [0]) * n
        for i in range(n):
            env = min(1.0, i / 2400, (n - i) / 2400)
            out[i] = int(2500 * env * math.sin(2 * math.pi * f * i / RATE))
        self.peticiones += 1
        self.caracteres += len(texto)
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
            return a
        return None

    def guarda(self, texto, k, a):
        self.ruta(texto, k).write_bytes(a.tobytes())


def locuta_bloque(motor: Motor, cache: Cache, texto: str, k: str, intentos: int = 6) -> array.array:
    guardado = cache.lee(texto, k)
    if guardado is not None:
        return guardado
    espera = 20.0
    fallos_minuto = 0
    mejor = None
    calidad = 0
    for intento in range(1, intentos + 1):
        try:
            a = recorta(motor.locuta(texto, k))
        except Exception as e:  # noqa: BLE001
            codigo, msg = motor.error(e)
            tipo = clasifica(codigo, msg)
            if tipo == "dia":
                raise CuotaAgotada(msg[:300]) from e
            if tipo == "fatal":
                raise ErrorFatal(msg[:500]) from e
            if tipo == "minuto":
                fallos_minuto += 1
                if fallos_minuto > 8:
                    raise CuotaAgotada("demasiados avisos de límite por minuto: " + msg[:200]) from e
                log(f"  límite de peticiones; espero {int(espera)} s")
                time.sleep(espera)
                espera = min(espera * 1.6, 120)
                continue
            log(f"  error ({codigo}): {msg[:160]}; reintento {intento}/{intentos}")
            time.sleep(min(5 * intento, 30))
            continue
        dur = len(a) / RATE
        cps = len(texto) / dur if dur > 0 else 999
        # Una locución normal en castellano va a 11-19 caracteres por segundo. Muy rápida suele
        # indicar que se ha comido texto; muy lenta, que ha añadido algo o dejado silencios largos.
        minimo = 5.5 if len(texto) < 40 else 8.0
        ok = minimo <= cps <= 26.0
        if ok:
            cache.guarda(texto, k, a)
            return a
        log(f"  duración sospechosa ({dur:.1f} s para {len(texto)} caracteres, {cps:.1f} c/s); repito")
        if mejor is None or abs(cps - 15) < abs(calidad - 15):
            mejor, calidad = a, cps
    if mejor is None:
        raise RuntimeError("no se ha podido locutar el bloque tras varios intentos")
    log("  se acepta la mejor toma disponible")
    cache.guarda(texto, k, mejor)
    return mejor


# ---------------------------------------------------------------- manifiesto

def nombre_mp3(clave: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", clave) + ".mp3"


def lee_json(p: Path, defecto):
    if p.exists():
        return json.loads(p.read_text("utf-8"))
    return defecto


def escribe_json(p: Path, d):
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", "utf-8")
    tmp.replace(p)


def firma_voz(args) -> str:
    base = f"{args.modelo}|{args.voz}|{hashlib.sha1(ESTILO_BASE.encode()).hexdigest()[:10]}"
    return "prueba|" + base if args.motor == "prueba" else base


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--motor", choices=sorted(MOTORES), default="gemini")
    ap.add_argument("--modelo", default=os.environ.get("VOZ_MODELO", MODELO))
    ap.add_argument("--voz", default=os.environ.get("VOZ_NOMBRE", VOZ))
    ap.add_argument("--textos", default=str(AQUI / "textos.json"))
    ap.add_argument("--salida", default=str(AQUI))
    ap.add_argument("--solo", default="", help="claves separadas por comas (cap:sabemos,pj:P001)")
    ap.add_argument("--max-pistas", type=int, default=0, help="0 = sin límite")
    ap.add_argument("--rpm", type=float, default=float(os.environ.get("VOZ_RPM", "0")),
                    help="peticiones por minuto como máximo (0 = sin pausa entre peticiones)")
    ap.add_argument("--forzar", action="store_true", help="regenera aunque la huella coincida")
    ap.add_argument("--hilos", type=int, default=int(os.environ.get("VOZ_HILOS", "4")),
                    help="bloques que se piden a la vez (1 = de uno en uno)")
    ap.add_argument("--limite-minutos", type=float, default=0,
                    help="no empieza pistas nuevas pasado este tiempo (0 = sin límite)")
    ap.add_argument("--cache", default=str(AQUI / ".cache"))
    ap.add_argument("--fijar-base", default=None, help="solo reescribe la base de audio.json y sale")
    ap.add_argument("--podar", action="store_true", help="borra del manifiesto y del disco las pistas que ya no existen en la web")
    args = ap.parse_args(argv)

    salida = Path(args.salida)
    man_p = salida / "audio.json"
    man = lee_json(man_p, {"esquema": "4.6", "base": "", "voz": {}, "pistas": {}})
    man.setdefault("pistas", {})

    if args.fijar_base is not None:
        man["base"] = args.fijar_base.rstrip("/")
        escribe_json(man_p, man)
        log(f"base = {man['base']}")
        return 0

    textos = lee_json(Path(args.textos), None)
    if not textos:
        raise SystemExit(f"No existe {args.textos}; ejecute antes extraer_textos.mjs")
    pistas = textos["pistas"]
    vivas = {t["clave"] for t in pistas}

    if args.podar:
        for clave in list(man["pistas"]):
            if clave not in vivas:
                src = man["pistas"][clave].get("src")
                if src and (salida / src).exists():
                    (salida / src).unlink()
                del man["pistas"][clave]
                log(f"podada {clave}")

    firma = firma_voz(args)
    solo = {s.strip() for s in args.solo.split(",") if s.strip()}
    pendientes = []
    for t in pistas:
        if solo and t["clave"] not in solo:
            continue
        ya = man["pistas"].get(t["clave"])
        if (not args.forzar and ya and ya.get("huella") == t["huella"] and ya.get("firma") == firma
                and (salida / ya.get("src", "")).exists()):
            continue
        pendientes.append(t)
    if args.max_pistas > 0:
        pendientes = pendientes[: args.max_pistas]

    total_c = sum(t["chars"] for t in pendientes)
    log(f"{len(pendientes)} pistas por locutar ({total_c} caracteres) con {args.motor} · {args.modelo} · voz {args.voz}")
    if not pendientes:
        escribe_json(man_p, man)
        return 0

    motor = MOTORES[args.motor](args)
    cache = Cache(Path(args.cache) / re.sub(r"[^A-Za-z0-9]+", "_", firma), firma)
    man["voz"] = {
        "motor": "Google Gemini TTS" + (" (vía OpenRouter)" if args.motor == "openrouter" else ""),
        "modelo": args.modelo,
        "voz": args.voz,
        "aviso": "Locución con voz sintética generada por IA (Google Gemini).",
    }
    if args.motor == "prueba":
        man["voz"].update({"motor": "Prueba (tonos sin voz)", "aviso": "Pista de prueba: tonos sin voz."})

    hechas = 0
    codigo_salida = 0
    inicio = time.time()
    try:
        for n, t in enumerate(pendientes, 1):
            if args.limite_minutos and time.time() - inicio > args.limite_minutos * 60:
                log(f"Límite de {args.limite_minutos:.0f} min alcanzado; el resto queda para la próxima ejecución.")
                break
            log(f"[{n}/{len(pendientes)}] {t['clave']} · {t['titulo']} · {len(t['bloques'])} bloques, {t['chars']} caracteres")
            with ThreadPoolExecutor(max_workers=max(1, args.hilos)) as ex:
                futuros = [ex.submit(locuta_bloque, motor, cache, b["x"], b["k"]) for b in t["bloques"]]
                audios = [f.result() for f in futuros]
            piezas, marcas = [silencio(INICIO)], []
            pos = len(piezas[0])
            for i, b in enumerate(t["bloques"]):
                if i > 0:
                    s = silencio(pausa(t["bloques"][i - 1]["k"], b["k"]))
                    piezas.append(s)
                    pos += len(s)
                a = audios[i]
                marcas.append(round(pos / RATE, 2))
                piezas.append(a)
                pos += len(a)
            piezas.append(silencio(FINAL))
            pista = array.array("h")
            for p in piezas:
                pista.extend(p)
            pista = normaliza(pista)
            src = "mp3/" + nombre_mp3(t["clave"])
            a_mp3(pista, salida / src, t["titulo"], man["voz"]["aviso"])
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
            for b in t["bloques"]:  # la pista ya está en el MP3: sus bloques sueltos sobran
                cache.ruta(b["x"], b["k"]).unlink(missing_ok=True)
            hechas += 1
            log(f"  ✓ {src} · {man['pistas'][t['clave']]['dur']:.0f} s")
    except CuotaAgotada as e:
        log(f"Cuota agotada por hoy: {e}")
        log("Se han guardado las pistas terminadas; la próxima ejecución continúa donde se quedó.")
    except ErrorFatal as e:
        log(f"ERROR: {e}")
        codigo_salida = 2
    finally:
        escribe_json(man_p, man)
        log(f"Pistas terminadas en esta ejecución: {hechas}. Peticiones: {motor.peticiones}. "
            f"Caracteres enviados: {motor.caracteres}.")
        faltan = [t["clave"] for t in pistas if (man["pistas"].get(t["clave"]) or {}).get("huella") != t["huella"]]
        log(f"Pistas pendientes en total: {len(faltan)} de {len(pistas)}.")
    return codigo_salida


if __name__ == "__main__":
    sys.exit(main())
