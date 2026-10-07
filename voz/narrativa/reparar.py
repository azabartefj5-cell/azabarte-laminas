#!/usr/bin/env python3
"""Repara locuciones ya publicadas sin volver a pedirlas a Google (07-10-2026).

El investigador oyó en el libro tomas que decían en voz alta «long pause» o «pausa larga» (el separador de párrafos
que se mandaba a Gemini hasta ese día) y respiraciones largas antes de algunos párrafos. Este script, para cada pista:

  1. la transcribe con faster-whisper (marcas de tiempo por palabra) y busca palabras de la dirección que no están en
     el texto («pausa», «long», «silencio»…; las mismas de locutar.INTRUSAS);
  2. corta cada racha de esas palabras («larga pausa, larga pausa») desde donde acaba la voz anterior hasta donde
     empieza la siguiente, dejando entre las dos como mucho PAUSA_MAX de silencio;
  3. silencia las respiraciones (locutar.quita_respiraciones);
  4. recoloca las marcas del resaltado, guarda el MP3 (a 96 kb/s, para no perder calidad al recodificar) y lo anota en
     audio.json, quitando la «base» de la pista para que publicar.sh la clave al commit nuevo.

Uso:
  python reparar.py lib:actas lib:guerra          # repara esas pistas
  python reparar.py --todas                        # todas las del manifiesto
  python reparar.py lib:actas --solo-informe       # dice qué haría, sin tocar nada
Después, publicar con la Action (un push de voz/narrativa la lanza) o con publicar.sh.
"""
from __future__ import annotations

import argparse
import array
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

import locutar as L

PAUSA_MAX = 1.4  # segundos de silencio, como mucho, donde estaba la palabra intrusa
KBPS_REPARADO = 96


def lee_pcm(mp3: Path) -> array.array:
    r = subprocess.run([L.ffmpeg_bin(), "-v", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1", "-ar", str(L.RATE),
                        "-"], capture_output=True, check=True)
    a = array.array("h")
    a.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    return a


_MODELO = {}


def palabras_con_tiempo(a: array.array):
    import numpy as np
    from faster_whisper import WhisperModel  # type: ignore
    if "m" not in _MODELO:
        _MODELO["m"] = WhisperModel("small", device="cpu", compute_type="int8")
    x = np.frombuffer(a.tobytes(), dtype=np.int16).astype(np.float32) / 32768.0
    x = np.interp(np.arange(0, len(x), L.RATE / 16000), np.arange(len(x)), x).astype(np.float32)
    segs, _ = _MODELO["m"].transcribe(x, language="es", word_timestamps=True, vad_filter=True, beam_size=5,
                                      condition_on_previous_text=False)
    return [{"w": w.word.strip(), "s": w.start, "e": w.end} for s in segs for w in (s.words or [])]


def busca_intrusas(words, texto):
    en_texto = {}
    for w in L._palabras(texto):
        en_texto[w] = en_texto.get(w, 0) + 1
    vistas, malas = {}, []
    for i, w in enumerate(words):
        for p in L._palabras(w["w"]):
            vistas[p] = vistas.get(p, 0) + 1
            if any(p.startswith(x) for x in L.INTRUSAS) and vistas[p] > en_texto.get(p, 0):
                malas.append(i)
                break
    return malas


COMPANERAS = ("larg", "llarg", "llan", "long", "paus", "pauz", "silenc")
PEGAMENTO = {"a", "de", "y", "e", "o", "la", "el"}  # Whisper oye «largo a pausa»
SUELTAS = {"pos", "pause"}  # y «Long Pos»: van en la racha, también al final


def niveles(a):
    """dBFS de cada trama de 20 ms."""
    import numpy as np
    fr = int(L.TRAMA * L.RATE)
    x = np.frombuffer(a.tobytes(), dtype=np.int16).astype(np.float32) / 32768.0
    n = len(x) // fr
    return 20 * np.log10(np.sqrt((x[: n * fr].reshape(n, fr) ** 2).mean(1)) + 1e-9)


def grupos_intrusos(words, malas):
    """Rachas de palabras de la dirección alrededor de cada intrusa (p. ej. «larga pausa, larga pausa»): (i, j)."""
    def es_dir(k):
        ps = L._palabras(words[k]["w"])
        return bool(ps) and all(any(p.startswith(c) for c in COMPANERAS) or p in PEGAMENTO or p in SUELTAS for p in ps)
    out = []
    for m in malas:
        i = j = m
        while i > 0 and es_dir(i - 1):
            i -= 1
        while j + 1 < len(words) and es_dir(j + 1):
            j += 1
        while i < m and L._palabras(words[i]["w"])[0] in PEGAMENTO:
            i += 1
        while j > m and L._palabras(words[j]["w"])[-1] in PEGAMENTO:
            j -= 1
        if not out or i > out[-1][1]:
            out.append((i, j))
    return out


def tramo_a_cortar(a, d, words, i, j):
    """(ini, fin) en segundos que se quitan por la racha words[i..j]: desde donde acaba de verdad la voz anterior (+0,2 s)
    hasta donde empieza la siguiente, dejando como mucho PAUSA_MAX de silencio entre las dos."""
    tr = L.TRAMA
    total = len(d) * tr
    antes = words[i - 1]["e"] if i > 0 else 0.0
    despues = words[j + 1]["s"] if j + 1 < len(words) else total
    # fin real de la voz anterior: última trama sonora (> -45 dBFS) antes de la racha
    k = int(words[i]["s"] / tr) - 3
    tope = int(antes / tr)
    while k > tope and d[k] < -45:
        k -= 1
    fin_voz = max(antes, (k + 1) * tr)
    # comienzo real de la voz siguiente: primera trama sonora desde un poco antes de la palabra
    k = max(int(words[j]["e"] / tr) + 3, int((despues - 0.3) / tr))
    while k < len(d) and d[k] < -45:
        k += 1
    ini_voz = min(despues, k * tr) if j + 1 < len(words) else total
    ini = min(fin_voz + 0.2, words[i]["s"] - 0.05)
    fin = max(ini_voz - (PAUSA_MAX - 0.2), words[j]["e"] + 0.05)
    return ini, fin


def corta(a, cortes, marcas):
    """Quita los tramos [ini, fin) (segundos) y recoloca las marcas: la que caía dentro pasa al punto del corte."""
    quitar = sorted(cortes)
    out, pos = array.array("h"), 0
    for ini, fin in quitar:
        i0, i1 = int(ini * L.RATE), int(fin * L.RATE)
        out.extend(a[pos:i0])
        pos = max(pos, i1)
    out.extend(a[pos:])

    def nuevo(t):
        quitado = 0.0
        for ini, fin in quitar:
            if t >= fin:
                quitado += fin - ini
            elif t > ini:
                return round(ini - quitado, 2)
        return round(t - quitado, 2)
    return out, [nuevo(t) for t in marcas]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("claves", nargs="*")
    ap.add_argument("--todas", action="store_true")
    ap.add_argument("--salida", default=str(L.AQUI))
    ap.add_argument("--textos", default=str(L.AQUI / "textos.json"))
    ap.add_argument("--palabras", default="", help="carpeta con <clave>.json de una transcripción previa ({words:[…]})")
    ap.add_argument("--solo-informe", action="store_true")
    args = ap.parse_args(argv)
    salida = Path(args.salida)
    man_p = salida / "audio.json"
    man = json.loads(man_p.read_text("utf-8"))
    textos = {t["clave"]: t for t in json.loads(Path(args.textos).read_text("utf-8"))["pistas"]}
    claves = list(man["pistas"]) if args.todas else args.claves
    if not claves:
        ap.error("indique las pistas o --todas")
    hoy = _dt.date.today().isoformat()
    for clave in claves:
        p = man["pistas"].get(clave)
        if not p or clave not in textos:
            L.log(f"{clave}: no está en el manifiesto o en los textos; se salta")
            continue
        if p.get("huella") != textos[clave]["huella"]:
            L.log(f"{clave}: el texto de la web ha cambiado desde la grabación; se regrabará, no se repara")
            continue
        a = lee_pcm(salida / p["src"])
        texto = " ".join(b["x"] for b in textos[clave]["bloques"])
        prev = Path(args.palabras) / (clave.replace(":", "_") + ".json") if args.palabras else None
        words = json.loads(prev.read_text("utf-8"))["words"] if prev and prev.exists() else palabras_con_tiempo(a)
        d = niveles(a)
        cortes, dichos = [], []
        for i, j in grupos_intrusos(words, busca_intrusas(words, texto)):
            ini, fin = tramo_a_cortar(a, d, words, i, j)
            cortes.append((ini, fin))
            dichos.append(f"{ini:.1f}-{fin:.1f} s «{' '.join(w['w'] for w in words[i:j + 1])}»")
        L.log(f"{clave}: {len(cortes)} cortes" + (": " + "; ".join(dichos) if dichos else ""))
        if args.solo_informe:
            continue
        b, marcas = corta(a, cortes, p["marcas"]) if cortes else (a, p["marcas"])
        b = L.quita_respiraciones(b)
        if not cortes and b == a:
            L.log("  nada que reparar")
            continue
        L.a_mp3(b, salida / p["src"], p.get("titulo", clave), man.get("voz", {}).get("aviso", ""), kbps=KBPS_REPARADO)
        p.update({"marcas": marcas, "dur": round(len(b) / L.RATE, 2), "bytes": (salida / p["src"]).stat().st_size,
                  "reparado": hoy + (f": {len(cortes)} cortes de dirección leída y respiraciones" if cortes
                                     else ": respiraciones")})
        p.pop("base", None)  # publicar.sh le pondrá la del commit nuevo
        L.escribe_json(man_p, man)
        L.log(f"  ✓ {p['src']} · {p['dur']:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
