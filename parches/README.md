# Parches para la web (azabarte.com)

La web se despliega en Vercel desde una carpeta local (no desde este repositorio),
así que los cambios de código se dejan aquí como parches listos para aplicar
sobre esa carpeta.

## personajes-apellidos-completos.patch

**Qué corrige.** En los rótulos cortos de los personajes (tira «Otros personajes»,
rostros de la serie alavesa, fichas breves de los capítulos, reparto de la edición
narrativa, chips del mapa y de la cadena documental) solo se veía el nombre de pila,
y en varios casos ni siquiera el apellido: «Martín de Barchín», «Francisco de
Buenache», «Catalina de Toledo», «Antonio el viejo», «José de Angiozar», «María de la
Valldigna»… quedaban sin su Zabarte, Zabartte o Azabarte. Ahora todos los personajes
muestran todos sus apellidos y la grafía del apellido (Azabarte, Zabarte, Asabarte,
Azavarte, Sabarte, Çabarte, Zabartte, Zauartte) va resaltada en dorado, como ya
ocurría solo en el título de la ficha.

Cambios en `public/app.js`:

- `pjApellido(p)`: nuevo cálculo de los apellidos. Se localiza el nombre corto dentro
  del nombre completo (palabra a palabra, sin distinguir mayúsculas); si no está,
  se quitan solo las palabras iniciales comunes y las partículas (de, del, la, y)
  se quedan con el apellido. Los paréntesis con una grafía («Pedro Azabarte
  (Azavarte)») se conservan; los demás («hijo de Venus») se omiten.
- `marcaGrafia(html)`: resalta todas las grafías del apellido en un texto ya escapado.
  Sustituye la expresión antigua, que solo conocía Azabarte, Zabarte y Asabarte.
- `pjRotulo(p)`: rótulo común (nombre corto en negrita y debajo todos los apellidos)
  usado en la tira de personajes, los rostros de Álava y las fichas breves de capítulo.
- Chips en línea (mapa, lugar, cadena documental, reparto narrativo, mapa del camino):
  pasan a mostrar el nombre completo.
- Galería (`viewPersonajes` y `pnCard`) y título de la ficha: el nombre completo con
  la grafía resaltada.

Cambio en `public/index.html` (una regla de CSS junto a `.pj-hero h1 em`):

    .pcard h3 em,.pn-card-h em,.ape em,.legacy .strip a .ape em{display:inline;font-style:normal;font-size:inherit;color:var(--gold-deep);margin:0}

Si `index.html` se genera a partir de una plantilla, añadir esa regla en la plantilla.

## Cómo aplicar

Desde la carpeta de la web (la que contiene `public/` y `api/`):

    patch -p1 < /ruta/a/azabarte-laminas/parches/personajes-apellidos-completos.patch

Después, regenerar `index.html` si el proceso de construcción incrusta `app.js`, y
desplegar como de costumbre.

## Comprobación

Se ha aplicado sobre los ficheros publicados el 27-09-2026 y se ha comprobado con
los 55 personajes actuales: todos los que tienen apellido distinto del nombre corto
lo muestran (los seis restantes ya llevan el nombre completo en el corto: Francisco
Navarro, Tomasa Fides, Juan Fides, Tomasa Calvo, Francisco de Carlos, Camila). La
galería, la ficha y la tira se han renderizado en Chromium sin errores de JavaScript.
