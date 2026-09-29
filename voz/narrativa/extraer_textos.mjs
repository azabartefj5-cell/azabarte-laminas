#!/usr/bin/env node
/* Extrae de la web publicada los textos que lee el reproductor «Escuchar» de la edición narrativa.
 *
 * No reescribe las reglas de extracción: toma de la propia página las funciones del bloque
 * VZ-TEXTO (vzLimpia, vzBloquesCapitulo, vzBloquesRelato, vzTextoCanonico) y los datos
 * (window.APP_DATA), y enumera las pistas igual que pistaDeRuta() del módulo voz.js:
 *   - cap:<id>  cada capítulo de narrativa.capitulos con al menos 2 bloques;
 *   - pj:<id>   cada personaje con relato narrativo (nombre, entradilla, relato) y al menos 3 bloques;
 *   - bio:<id>  el personaje sin relato narrativo (nombre, primera frase de la bio, resto de la bio).
 *   - lib:<id>  cada capítulo del libro continuo «Antes de nosotros» (narrativa.libro, desde el 29-09-2026).
 * La huella es el SHA-256 hex del texto canónico, la misma que calcula el navegador con
 * crypto.subtle; el reproductor solo usa una grabación si su huella coincide con el texto actual.
 *
 * Uso:
 *   node extraer_textos.mjs [--url https://azabarte.com/] [--html index.html] [--salida textos.json]
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const opt = (name, def) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : def; };
const URL_WEB = opt('url', 'https://azabarte.com/');
const HTML = opt('html', null);
const SALIDA = opt('salida', path.join(path.dirname(fileURLToPath(import.meta.url)), 'textos.json'));

async function leeHtml() {
  if (HTML) return { html: fs.readFileSync(HTML, 'utf8'), origen: URL_WEB };
  const r = await fetch(URL_WEB, { headers: { 'user-agent': 'azabarte-voz-narrativa/1.0' } });
  if (!r.ok) throw new Error(`No se puede descargar ${URL_WEB}: HTTP ${r.status}`);
  return { html: await r.text(), origen: URL_WEB };
}

function scriptPorId(html, id) {
  const m = new RegExp(`<script id="${id}"[^>]*>([\\s\\S]*?)</script>`).exec(html);
  if (!m) throw new Error(`La página no contiene <script id="${id}">`);
  return m[1];
}

function datosApp(html) {
  const code = scriptPorId(html, 'app-data');
  // Los datos son JSON tras «window.APP_DATA =» (le sigue window.APP_ASSETS). Se leen como JSON:
  // un «;» seguido de salto de línea no puede estar dentro de una cadena JSON. Si falla, se evalúan.
  const cuerpo = code.replace(/^\s*window\.APP_DATA\s*=\s*/, '');
  const fin = cuerpo.search(/;+[ \t]*\r?\n/);
  try { return JSON.parse((fin >= 0 ? cuerpo.slice(0, fin) : cuerpo).replace(/[\s;]+$/, '')); } catch (e) { /* sigue abajo */ }
  const ctx = { window: {} };
  vm.runInNewContext(code, ctx, { timeout: 20000 });
  const D = ctx.window.APP_DATA || ctx.APP_DATA;
  if (!D) throw new Error('No se encuentra window.APP_DATA');
  return D;
}

function funcionesTexto(html) {
  const code = scriptPorId(html, 'app-script');
  const m = /\/\*VZ-TEXTO-INICIO\*\/([\s\S]*?)\/\*VZ-TEXTO-FIN\*\//.exec(code);
  if (!m) throw new Error('El script de la página no tiene el bloque VZ-TEXTO');
  const ctx = {};
  vm.runInNewContext(m[1] + "\n;this.F={vzLimpia,vzBloquesCapitulo,vzBloquesRelato,vzTextoCanonico,vzBloquesLibro:(typeof vzBloquesLibro==='function'?vzBloquesLibro:null)};", ctx, { timeout: 5000 });
  return ctx.F;
}

const sha256 = (t) => crypto.createHash('sha256').update(Buffer.from(t, 'utf8')).digest('hex');

function pistas(D, F) {
  const NARR = D._edicion === 'narrativa';
  const NR = D.narrativa || {};
  const NRP = (id) => (NR.personajes || {})[id] || {};
  const out = [];
  if (NARR) {
    for (const [id, N] of Object.entries(NR.capitulos || {})) {
      const b = F.vzBloquesCapitulo(N);
      if (b.length < 2) continue;
      out.push({ clave: 'cap:' + id, titulo: N.t || id, tipo: 'cap', bloques: b });
    }
  }
  // El libro continuo «Antes de nosotros» (29-09-2026): una pista por capítulo, en el orden del libro.
  // Una página anterior, sin vzBloquesLibro, simplemente no da pistas lib:.
  const L = NR.libro;
  if (NARR && F.vzBloquesLibro && L && Array.isArray(L.capitulos)) {
    L.capitulos.forEach((C, i) => {
      if (!C || !C.id) return;
      const b = F.vzBloquesLibro(L, i);
      if (b.length < 2) return;
      out.push({ clave: 'lib:' + C.id, titulo: [C.rotulo, C.t].filter(Boolean).join(' · '), tipo: 'lib', bloques: b });
    });
  }
  for (const p of ((D.personajes || {}).personajes || [])) {
    const R = NARR ? NRP(p.id) : {};
    const conRelato = !!(NARR && R.relato && R.relato.length);
    const bio = p.bio || [];
    const lede = (NARR && R.lede) || bio[0] || '';
    const cuerpo = conRelato ? R.relato : bio.slice(1);
    const bl = F.vzBloquesRelato(p.nombre, lede, cuerpo);
    if (bl.length < 3) continue;
    out.push({ clave: (conRelato ? 'pj:' : 'bio:') + p.id, titulo: p.corto || p.nombre, tipo: 'pj', bloques: bl });
  }
  for (const t of out) {
    t.bloques = t.bloques.map((b) => ({ k: b.k, x: b.x }));
    t.huella = sha256(F.vzTextoCanonico(t.bloques));
    t.chars = t.bloques.reduce((n, b) => n + b.x.length, 0);
  }
  return out;
}

const { html, origen } = await leeHtml();
const D = datosApp(html);
const F = funcionesTexto(html);
const lista = pistas(D, F);
// Freno: si la página no es la edición narrativa o llega incompleta, no se escribe nada. Así la
// locución no se pone a grabar otra edición ni la poda borra las grabaciones buenas.
if (D._edicion !== 'narrativa') throw new Error(`La página no es la edición narrativa (edición «${D._edicion}»)`);
if (!lista.some((t) => t.tipo === 'cap')) throw new Error('La página no trae capítulos narrativos');
const doc = {
  origen,
  edicion: D._edicion || null,
  total_pistas: lista.length,
  total_caracteres: lista.reduce((n, t) => n + t.chars, 0),
  pistas: lista,
};
fs.writeFileSync(SALIDA, JSON.stringify(doc, null, 1) + '\n');
console.log(`${lista.length} pistas, ${doc.total_caracteres} caracteres → ${SALIDA}`);
