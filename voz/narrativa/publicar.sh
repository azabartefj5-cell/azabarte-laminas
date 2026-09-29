#!/usr/bin/env bash
# Publica las locuciones de voz/narrativa en la rama actual: primero los MP3 y los textos, después el manifiesto
# audio.json con la base del CDN (jsDelivr) clavada a un commit que tenga esos mismos MP3, y por último purga la
# caché del manifiesto en jsDelivr. Lo usa la Action (al locutar y cuando llega audio nuevo a la rama).
#
# Necesita: GITHUB_REPOSITORY, GITHUB_REF_NAME, GH_TOKEN (para subir). Opcional: PURGA_SIEMPRE=1 purga aunque
# el manifiesto no cambie (cuando el audio lo ha subido otra persona o sesión).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
# Identidad del bot solo si no hay otra (en la Action no la hay; en una sesión local se respeta la suya).
git config user.name >/dev/null || git config user.name "github-actions[bot]"
git config user.email >/dev/null || git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
if [ -n "${GH_TOKEN:-}" ]; then
  git remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
fi
empuja() {
  for i in 1 2 3 4 5; do
    if git pull --rebase --autostash origin "$GITHUB_REF_NAME" && git push origin "HEAD:$GITHUB_REF_NAME"; then return 0; fi
    echo "No se ha podido subir (intento $i); reintento."; sleep $((i * 10))
  done
  return 1
}
purga() {
  curl -fsS "https://purge.jsdelivr.net/gh/${GITHUB_REPOSITORY}@${GITHUB_REF_NAME}/voz/narrativa/audio.json" \
    || echo "No se ha podido purgar la caché de jsDelivr; se renovará sola en unas horas."
}
# 1) Los MP3 y los textos primero; el manifiesto aún no, para que nunca apunte a MP3 que no están.
git add -A voz/narrativa
git reset -q voz/narrativa/audio.json
if ! git diff --cached --quiet; then
  git commit -m "Voz narrativa: locuciones con Gemini TTS ($(date -u +%F))"
  empuja
fi
# 2) La base del manifiesto debe ser un commit con estos mismos MP3.
if [ -n "$(ls -A voz/narrativa/mp3 2>/dev/null | grep -v '^\.' || true)" ]; then
  BASE=$(python3 -c "import json;print(json.load(open('voz/narrativa/audio.json')).get('base',''))")
  BASE_SHA=$(printf '%s' "$BASE" | sed -n 's#.*@\([0-9a-f]\{40\}\)/.*#\1#p')
  ACTUAL=$(git rev-parse HEAD:voz/narrativa/mp3)
  PREVIO=$( [ -n "$BASE_SHA" ] && git rev-parse "$BASE_SHA:voz/narrativa/mp3" 2>/dev/null || true )
  if [ "$PREVIO" != "$ACTUAL" ]; then
    SHA=$(git rev-parse HEAD)
    python3 voz/narrativa/locutar.py --fijar-base "https://cdn.jsdelivr.net/gh/${GITHUB_REPOSITORY}@${SHA}/voz/narrativa"
  fi
fi
# Calentar (29-09-2026): jsDelivr trae cada fichero de GitHub la primera vez que alguien lo pide, y eso tarda
# de 3 a 6 s por MP3 (41 s el primero de un commit). Se pide aquí cada MP3 recién publicado para que esa espera
# la pague la Action y no el primer oyente. Seis a la vez; un fallo no para nada.
calienta() {
  python3 - <<'PY' | xargs -r -P 6 -I{} sh -c 'if curl -fsS -o /dev/null --retry 3 --max-time 300 "{}"; then echo "  caliente: {}"; else echo "  sin calentar: {}"; fi'
import json
m = json.load(open("voz/narrativa/audio.json", encoding="utf-8"))
b = (m.get("base") or "").rstrip("/")
for p in (m.get("pistas") or {}).values():
    if isinstance(p, dict) and p.get("src") and (p.get("base") or b).rstrip("/") == b and b:
        print(b + "/" + p["src"])
PY
}
# 3) El manifiesto.
git add voz/narrativa/audio.json
if ! git diff --cached --quiet; then
  git commit -m "Voz narrativa: manifiesto de las locuciones"
  empuja
  purga
  echo "Calentando en jsDelivr los audios recién publicados…"
  calienta || true
elif [ "${PURGA_SIEMPRE:-}" = "1" ]; then
  echo "El manifiesto ya estaba al día; se purga la caché para que se vea."
  purga
else
  echo "El manifiesto no cambia."
fi
