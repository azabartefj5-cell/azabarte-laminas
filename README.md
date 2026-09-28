# Láminas animadas del Proyecto Origen Azabarte

Cinemagrafías (mp4, 8 s, sin música) de las láminas de capítulo y de los monumentos
de Las Pedroñeras y Ondategi que ilustran la investigación sobre el origen del
apellido Azabarte. La web las carga desde jsDelivr:

    https://cdn.jsdelivr.net/gh/<usuario>/azabarte-laminas@<commit>/img/monumentos/<id>.mp4

Este repositorio aloja los vídeos y la voz de la edición narrativa; el sitio vive en https://azabarte.com.

## Voz de la edición narrativa

`voz/narrativa/` guarda las locuciones de la edición narrativa leídas con la voz de Google (Gemini TTS), su
manifiesto `audio.json` y el generador. La Action «Locutar la edición narrativa» las crea y las publica por
jsDelivr en cuanto el repositorio tiene el secreto `GEMINI_API_KEY` u `OPENROUTER_API_KEY`. Detalles y parche
para la web en `voz/narrativa/README.md`.

## Parches para la web

En `parches/` se guardan los cambios de código de la web que se aplican sobre la carpeta
local desde la que se despliega (ver `parches/README.md`).
