# Poner Lacancito en internet

Para que un colega la use **sin instalar nada**: abre un link en el celular y
listo.

---

## Lo que no va a funcionar, para descartarlo

**La tienda de Google Play.** Requiere cuenta de desarrollador (25 dólares, una
vez), empaquetar la app, y pasar una revisión. Y la app seguiría necesitando la
base de 156 MB adentro. Es mucho trabajo para el mismo resultado.

**GitHub Pages.** Sólo publica páginas quietas. Lacancito necesita un programa
andando que busque en la base; Pages no ejecuta nada.

---

## Lo que sí: una dirección web

Un servicio que corra Python. La app ya está preparada: cuando detecta que está
en un servidor, escucha donde el servidor le indique en vez de abrir el
navegador.

Y no hace falta ninguna tienda para que quede como app en el teléfono. Al
abrir el link, el celular ofrece **«Agregar a la pantalla de inicio»** —en
Chrome está en el menú de los tres puntos—. Queda un ícono igual que cualquier
otra app, y abre sin la barra del navegador. Eso ya está configurado.

---

## El problema a resolver primero: la base

La base pesa **156 MB** y GitHub rechaza archivos de más de 100 MB. O sea que no
puede vivir en el repositorio junto con el código.

Tres maneras de resolverlo, de más simple a menos:

**A. Subirla como «Release».** Los Release de GitHub aceptan hasta 2 GB. En el
repositorio: pestaña *Releases* → *Create a new release* → arrastrás
`datos/lacancito.db` → *Publish*. Queda con una dirección fija, y el servidor la
baja sola al arrancar.

**B. Subirla a mano al servidor.** Algunos servicios tienen administrador de
archivos por web. Simple, pero hay que repetirlo cada vez que la rehagas.

**C. Achicarla.** Se puede: sacando el índice fonético baja bastante, pero se
pierde la búsqueda por sonido, que es lo mejor que tiene.

---

## Paso a paso con Render

Render tiene plan gratuito y se conecta directo al repositorio.

**1.** Subí la base como Release (opción A de arriba). Copiá la dirección del
archivo: botón derecho sobre el nombre → *Copiar dirección del enlace*. Termina
en `.db`.

**2.** Entrá a **render.com**, creá una cuenta con tu usuario de GitHub.

**3.** *New* → *Web Service* → elegí el repositorio `Lacancito`.

**4.** Completá:

| Campo | Qué poner |
|---|---|
| Language | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python app.py` |
| Instance Type | Free |

**5.** Antes de crear el servicio, bajá hasta **Environment Variables** →
*Add Environment Variable*:

| Key | Value |
|---|---|
| `LACANCITO_DB_URL` | la dirección del Release que copiaste en el paso 1 |

Con eso la app se baja la base sola la primera vez que arranca. No hay que
escribir ningún comando de descarga.

**6.** *Create Web Service*. La primera vez tarda unos minutos: instala Python,
baja la base y arranca. Al terminar te da una dirección tipo
`https://lacancito.onrender.com`.

Esa dirección es la que les pasás a tus colegas.

---

## Lo que hay que saber del plan gratuito

**Se duerme.** Si nadie la usa por 15 minutos, Render la apaga. La primera
visita después la despierta y tarda unos 30 segundos en responder. Las
siguientes van rápido. Se soluciona pagando (unos 7 dólares por mes) o
avisándoles a tus colegas que la primera carga demora.

**Memoria.** El plan gratuito da 512 MB de RAM. Lacancito con esta base entra,
pero si el corpus crece mucho habrá que mirar.

**Cada vez que rehagas la base** hay que subir el Release de nuevo y apretar
*Manual Deploy* en Render.

---

## Qué le decís a un colega

> Entrá a `https://lacancito.onrender.com` desde el celular.
> Si querés que te quede como app: menú de los tres puntos → *Agregar a la
> pantalla de inicio*.
> La primera vez puede tardar medio minuto en abrir.

Nada más. Sin instalar, sin descargar, sin Python.
