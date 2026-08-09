# -*- coding: utf-8 -*-
"""
Lacancito como página web, para usarlo sin escribir comandos.

Se arranca haciendo doble clic en Lacancito.bat, o desde una terminal con:

    python app.py

Levanta un servidor en esta misma computadora y abre el navegador solo. Lo
único que sale a internet es el enlace al traductor, y sólo cuando se aprieta.
Para cerrarlo, se cierra la ventana negra.

El servidor no arma las citas: manda los datos sueltos (obra, clase, página,
edición) y la página las escribe en el idioma elegido. Así el botón de idioma
no necesita volver a preguntar nada al servidor.
"""
import json
import os
import re
import socket
import sqlite3
import sys

import pymupdf
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "ingesta"))

from buscar import (DB, asegurar_indice, buscar, buscar_por_sonido,  # noqa: E402
                    contar, frase_cercania, recorte)
from fonetica import localizar                                       # noqa: E402

PUERTOS = [8765, 8766, 8767, 8768, 8080]

AYUDA_SIN_BASE = """Lacancito no trae los textos de Lacan: la base se arma con los PDF
que tengas vos. Es una sola vez y tarda unos minutos.

  1) python -m pip install pymupdf
  2) python ingesta/ingestar_todos.py "RUTA A TUS SEMINARIOS"
  3) python ingesta/fuentes.py --carpeta "RUTA A TUS SEMINARIOS"
  4) python ingesta/indexar_fonetica.py

El paso a paso esta en INSTALAR.md.
Si alguien te paso un archivo lacancito.db, ponelo en la carpeta
datos y con eso alcanza.
"""

# Hay dos bases posibles y la app se adapta sola a la que encuentre:
#   la completa   -> tiene la columna «texto»: muestra los pasajes
#   la pública    -> no la tiene: sólo puede decir dónde está cada cosa
# Se decide mirando la base, no con una opción, para que no se pueda publicar
# la versión con texto por haberse olvidado de un parámetro.
DB_ACTUAL = DB


def bajar_base_si_falta(destino):
    """En un servidor la base no viene con el codigo: pesa 156 MB y GitHub no
    acepta archivos de mas de 100 MB. Se sube aparte como «Release» y se indica
    su direccion en la variable LACANCITO_DB_URL; aca se baja al arrancar.

    Asi el que configura el servidor pone una direccion en una casilla, en vez
    de escribir un comando de descarga a mano."""
    url = (os.environ.get("LACANCITO_DB_URL") or "").strip()
    if not url or os.path.exists(destino):
        return
    if not url.lower().startswith(("http://", "https://")):
        # El error típico: pegar la ruta del archivo en la propia computadora.
        # El servidor está en otra máquina y esa carpeta no existe para él.
        raise SystemExit(f"""
LACANCITO_DB_URL no es una dirección de internet:
  {url}

El servidor no puede ver los archivos de tu computadora. Hay que subir la
base a algún lado y poner acá su dirección, que empieza con https:// y
termina en .db. Si la subiste como Release de GitHub, se parece a esto:

  https://github.com/USUARIO/REPO/releases/download/base-v1/lacancito.db

Está explicado en PONERLA-EN-INTERNET.md.
""")
    import urllib.request
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    print(f"Bajando la base desde {url[:70]}…")
    parcial = destino + ".parcial"
    with urllib.request.urlopen(url) as r, open(parcial, "wb") as fh:
        total, leido = int(r.headers.get("Content-Length") or 0), 0
        while True:
            trozo = r.read(1 << 20)
            if not trozo:
                break
            fh.write(trozo)
            leido += len(trozo)
            if total:
                print(f"  bajando... {100 * leido // total}%", flush=True)
    # se renombra al final: si la descarga se corta, no queda una base a medias
    os.replace(parcial, destino)
    print(f"Base lista: {os.path.getsize(destino) / 1e6:.0f} MB")


def conexion():
    """Una conexión por pedido: el servidor atiende en varios hilos y una
    conexión de sqlite no se puede compartir entre hilos."""
    con = sqlite3.connect(DB_ACTUAL)
    con.row_factory = sqlite3.Row
    return con


def fila_a_dict(f, pasaje):
    return {
        "id": f["id"], "pasaje": pasaje, "obra": f["obra"],
        "escrito": f["escrito"], "sesion_n": f["sesion_n"],
        "sesion_fecha": f["sesion_fecha"], "pagina": f["pagina"],
        "aprox": f["pagina_confianza"] == "estimada", "capa": f["capa"],
        # el texto limpio y completo, para el enlace al traductor: el pasaje
        # que se muestra viene recortado y con las marcas del resaltado
        "texto": f["texto"], "idioma": f["idioma"],
        "familia": f["familia"], "dudosa": f["confianza"] == "dudosa",
        "pagina_pdf": f["pagina_pdf"],
    }


def api_buscar(p):
    q = (p.get("q", [""])[0] or "").strip()
    modo = p.get("modo", ["exacta"])[0]
    obra = p.get("obra", [""])[0] or None
    capa = p.get("capa", ["lacan"])[0]
    familia = p.get("familia", [""])[0] or None
    parte = {k: p.get(k, [""])[0] for k in ("escrito", "fecha", "sesion")}
    parte = {k: v for k, v in parte.items() if v} or None
    if parte and "sesion" in parte:
        parte["sesion"] = int(parte["sesion"])
    limite = min(int(p.get("limite", ["30"])[0]), 200)
    if not q:
        return {"resultados": [], "total": 0}

    con = conexion()
    try:
        if modo == "contar":
            por = p.get("por", ["obra"])[0]
            filas = contar(con, f'"{q}"' if " " in q else q, capa, por)
            maximo = max([f["n"] for f in filas], default=1)
            return {"modo": "contar", "total": sum(f["n"] for f in filas),
                    "grupos": [{"grupo": f["grupo"] or "?", "n": f["n"],
                                "parte": round(100 * f["n"] / maximo)}
                               for f in filas]}

        if modo == "sonido":
            son, filas, total, linea = buscar_por_sonido(
                con, q, capa, obra, limite, familia, parte)
            salida = []
            for f in filas:
                ubic = localizar(f["texto"], son)
                salida.append(fila_a_dict(
                    f, recorte(f["texto"], *ubic) if ubic else f["texto"][:300]))
            return {"modo": "sonido", "suena": son, "total": total,
                    "linea": linea, "resultados": salida}

        if modo == "cerca":
            # las palabras cerca una de otra, en cualquier orden
            consulta = frase_cercania(q, p.get("distancia", ["10"])[0])
            if not consulta:
                return {"error": "Para buscar por cercanía hacen falta "
                                 "al menos dos palabras."}
        else:
            # exacta: varias palabras sin comillas se toman como frase
            consulta = '"' + q.replace('"', "") + '"' if " " in q else q
        filas, total, linea = buscar(con, consulta, capa, obra, limite,
                                     familia, parte)
        return {"modo": modo, "total": total, "linea": linea,
                "resultados": [fila_a_dict(f, f["frag"]) for f in filas]}
    finally:
        con.close()


def api_contexto(p):
    id_frag = int(p.get("id", ["0"])[0])
    radio = min(int(p.get("radio", ["2"])[0]), 6)
    con = conexion()
    try:
        f = con.execute("SELECT * FROM segmento WHERE id = ?", (id_frag,)).fetchone()
        if not f:
            return {"vecinos": []}
        vecinos = con.execute(
            """SELECT * FROM segmento WHERE obra = ? AND capa = ?
               AND id BETWEEN ? AND ? ORDER BY id""",
            (f["obra"], f["capa"], id_frag - radio, id_frag + radio)).fetchall()
        return {"vecinos": [{"id": v["id"], "pagina": v["pagina"],
                             "texto": v["texto"], "foco": v["id"] == id_frag}
                            for v in vecinos]}
    finally:
        con.close()


def orden_de_obra(obra):
    """Para el desplegable: los seminarios por número, no alfabéticos, que es
    como los busca una persona. El 19b va justo después del 19."""
    m = re.match(r"Seminario\s+(\d+)(b?)", obra)
    if m:
        return (0, int(m.group(1)), 1 if m.group(2) else 0, obra)
    return (1, 0, 0, obra)


def api_catalogo():
    """Las obras para el desplegable, y de qué edición viene cada una."""
    con = conexion()
    try:
        obras = [r[0] for r in con.execute(
            "SELECT DISTINCT obra FROM segmento")]
        fuentes = {}
        try:
            for f in con.execute("SELECT * FROM fuente"):
                fuentes[f["obra"]] = dict(f)
        except sqlite3.OperationalError:
            pass                       # todavía no se corrió ingesta/fuentes.py

        # los seminarios por número; los libros por año de publicación, que es
        # el orden en que los busca alguien (Écrits 1966 antes que Autres 2001)
        def clave(o):
            base = orden_de_obra(o)
            if base[0] == 0:
                return base
            return (1, int((fuentes.get(o, {}).get("anios") or "9999")[:4]), 0, o)

        obras.sort(key=clave)
        def grupo(o):
            if o.startswith("Seminario"):
                return "sem"
            return "otr" if o == "Otros" else "esc"

        familias = [r[0] for r in con.execute(
            "SELECT DISTINCT familia FROM segmento WHERE familia IS NOT NULL"
            " ORDER BY familia")]
        # «Ver la página original» abre el PDF del que salió el fragmento. En un
        # servidor esos PDF no están: sólo viajó la base. Antes el botón se
        # mostraba igual y devolvía 404, justo en la función que sostiene la
        # promesa de contrastar contra el papel. Ahora el frente pregunta.
        hay_pdf = any(
            r[0] and os.path.exists(r[0])
            for r in con.execute("SELECT ruta FROM fuente WHERE ruta IS NOT NULL"))
        return {"obras": [{"obra": o, "grupo": grupo(o)} for o in obras],
                "familias": familias, "fuentes": fuentes,
                "hay_pdf": hay_pdf}
    finally:
        con.close()


def _serie_corpus(con):
    """Cuántas palabras tiene el corpus en cada año. Es el denominador: sin él
    sólo se puede contar en bruto, y en bruto 1967 gana siempre porque ese año
    Lacan habló más, no porque usara más la palabra."""
    return {r[0]: r[1] for r in con.execute(
        """SELECT substr(sesion_fecha,1,4),
                  sum(length(texto) - length(replace(texto,' ','')) + 1)
           FROM segmento WHERE capa='lacan' AND sesion_fecha IS NOT NULL
           GROUP BY 1""")}


def _gini(valores):
    """0 = repartido parejo; 1 = todo concentrado en un solo lugar.

    Se calcula sobre TASAS, no sobre conteos crudos. Sobre conteos mediría
    también la desigualdad de tamaño de las obras: un seminario largo tiene
    más de todo, y eso no dice nada sobre la concentración del término."""
    v = sorted(x for x in valores if x > 0)
    if len(v) < 2:
        return 1.0
    total = sum(v)
    acum = sum((i + 1) * x for i, x in enumerate(v))
    return round((2 * acum) / (len(v) * total) - (len(v) + 1) / len(v), 3)


RE_NO_LETRA = "(?<![a-z0-9])%s(?![a-z0-9])"


def _contar_ocurrencias(textos, termino):
    """Cuántas veces aparece de verdad, no en cuántos fragmentos.

    El motor de búsqueda devuelve fragmentos que contienen el término; un
    pasaje que lo dice tres veces cuenta uno solo. La diferencia no es chica
    ni pareja: va de 1,47 veces para «jouissance» a 1,67 para «sinthome», así
    que usar fragmentos como si fueran ocurrencias deforma la comparación
    entre términos. Acá se cuenta sobre el texto, palabra entera, como
    tokeniza el motor."""
    import unicodedata
    def pelar(t):
        return "".join(c for c in unicodedata.normalize("NFD", t.lower())
                       if unicodedata.category(c) != "Mn")
    partes = [w for w in re.findall(r"[\w'’]+", pelar(termino)) if w]
    if not partes:
        return 0
    # con varias palabras se cuenta la frase; con una, la palabra
    patron = re.compile(RE_NO_LETRA % r"[^a-z0-9]+".join(re.escape(w) for w in partes))
    return sum(len(patron.findall(pelar(t))) for t in textos)


def api_analisis(p):
    """Las cuentas de una palabra: cuándo, dónde, y qué tan concentrada."""
    q = (p.get("q", [""])[0] or "").strip()
    capa = p.get("capa", ["lacan"])[0]
    if not q:
        return {"series": []}
    con = conexion()
    try:
        asegurar_indice(con)
        salida = {"terminos": []}
        corpus = _serie_corpus(con)
        salida["corpus"] = [{"anio": a, "palabras": n} for a, n in sorted(corpus.items())]

        for termino in [x.strip() for x in q.split(",") if x.strip()][:3]:
            consulta = '"' + termino.replace('"', "") + '"' if " " in termino else termino
            cond = "" if capa == "todas" else " AND s.capa = :capa"
            base = f"""FROM busqueda JOIN segmento s ON s.id = busqueda.rowid
                       WHERE busqueda MATCH :q{cond}"""
            arg = {"q": consulta, "capa": capa}

            # se traen los textos que coinciden y se cuentan las ocurrencias
            # reales; con count(*) se contarían fragmentos, que es otra cosa
            filas_t = con.execute(
                f"SELECT s.sesion_fecha, s.obra, s.texto {base}", arg).fetchall()
            por_anio, por_obra_d, sin_fecha, fragmentos = {}, {}, 0, len(filas_t)
            for fecha, obra_f, texto in filas_t:
                n = _contar_ocurrencias([texto], termino)
                por_obra_d[obra_f] = por_obra_d.get(obra_f, 0) + n
                if fecha:
                    por_anio[fecha[:4]] = por_anio.get(fecha[:4], 0) + n
                else:
                    sin_fecha += n
            por_obra = [{"obra": o, "n": n} for o, n in
                        sorted(por_obra_d.items(), key=lambda x: -x[1])]
            # palabras de cada obra, para que la concentración no mida tamaños
            palabras_obra = {r[0]: r[1] for r in con.execute(
                "SELECT obra, sum(length(texto)-length(replace(texto,' ',''))+1)"
                " FROM segmento WHERE capa='lacan' GROUP BY 1")}
            tasas = [o["n"] / max(1, palabras_obra.get(o["obra"], 1))
                     for o in por_obra]
            n_obras = con.execute(
                "SELECT count(DISTINCT obra) FROM segmento WHERE capa='lacan'").fetchone()[0]

            anios = sorted(set(corpus) | set(por_anio))
            serie, acum = [], 0
            for a in anios:
                n = por_anio.get(a, 0)
                acum += n
                pal = corpus.get(a, 0)
                serie.append({"anio": a, "n": n, "acum": acum,
                              # por diez mil palabras: así 1953 y 1967 se comparan
                              "rel": round(10000 * n / pal, 2) if pal else None})
            pico = max(serie, key=lambda x: x["rel"] or 0, default=None)
            pico_abs = max(serie, key=lambda x: x["n"], default=None)
            conf = [x for x in serie if x["n"]]
            salida["terminos"].append({
                "termino": termino, "total": sum(por_obra_d.values()),
                "fragmentos": fragmentos, "sin_fecha": sin_fecha,
                "serie": serie, "por_obra": por_obra[:14],
                "primera": conf[0]["anio"] if conf else None,
                "ultima": conf[-1]["anio"] if conf else None,
                "pico_rel": pico["anio"] if pico and pico["rel"] else None,
                "pico_abs": pico_abs["anio"] if pico_abs and pico_abs["n"] else None,
                "obras_con": len(por_obra), "obras_total": n_obras,
                "gini": _gini(tasas),
            })
        return salida
    finally:
        con.close()


MANIFIESTO = {
    "name": "Lacancito", "short_name": "Lacancito",
    "description": "Buscador de citas de Lacan",
    "start_url": "/", "display": "standalone",
    "background_color": "#faf8f5", "theme_color": "#7a4b2a",
    "icons": [
        {"src": "/estatico/icono-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/estatico/icono-512.png", "sizes": "512x512", "type": "image/png"},
    ],
}


def render_pagina(p):
    """Dibuja la página original del PDF. Sirve para dos cosas: verificar una
    transcripción dudosa contra el papel, y ver los esquemas de los volúmenes
    escaneados, donde la figura es parte de la imagen de la página."""
    con = conexion()
    try:
        f = con.execute(
            "SELECT s.obra, s.pagina_pdf, fu.ruta FROM segmento s"
            " LEFT JOIN fuente fu ON fu.obra = s.obra WHERE s.id = ?",
            (int(p.get("id", ["0"])[0]),)).fetchone()
    finally:
        con.close()
    if not f or not f["ruta"] or not os.path.exists(f["ruta"]):
        return None
    doc = pymupdf.open(f["ruta"])
    n = max(0, min(f["pagina_pdf"] - 1, doc.page_count - 1))
    datos = doc[n].get_pixmap(dpi=int(p.get("dpi", ["150"])[0])).tobytes("png")
    doc.close()
    return datos


def api_partes(p):
    """El segundo nivel del desplegable: qué hay adentro de la obra elegida.

    Cambia según el tipo de obra, porque la unidad no es la misma: un seminario
    se recorre por clases, un volumen de Écrits por escritos, y «Otros» por
    piezas sueltas. Las piezas se identifican con título Y fecha: hay decenas
    de «Pneumatique à Pierre Soury» y sin la fecha se pisarían entre sí."""
    obra = p.get("obra", [""])[0]
    familia = p.get("familia", [""])[0] or None
    if not obra:
        return {"tipo": None, "partes": []}
    con = conexion()
    try:
        if obra.startswith("Seminario"):
            filas = con.execute(
                """SELECT sesion_n, sesion_fecha, count(*) n FROM segmento
                   WHERE obra = ? AND capa='lacan' AND sesion_n IS NOT NULL
                   GROUP BY sesion_n ORDER BY sesion_n""", (obra,)).fetchall()
            return {"tipo": "clase", "partes": [
                {"sesion": f["sesion_n"], "fecha": f["sesion_fecha"],
                 "etiqueta": None, "n": f["n"]} for f in filas]}
        if obra == "Otros":
            cond = " AND familia = ?" if familia else ""
            arg = (obra, familia) if familia else (obra,)
            filas = con.execute(
                f"""SELECT escrito, sesion_fecha, min(pagina) pag, count(*) n
                    FROM segmento WHERE obra = ? AND capa='lacan'{cond}
                    GROUP BY escrito, sesion_fecha
                    ORDER BY sesion_fecha, pag""", arg).fetchall()
            return {"tipo": "pieza", "partes": [
                {"escrito": f["escrito"], "fecha": f["sesion_fecha"],
                 "etiqueta": f["escrito"], "n": f["n"]} for f in filas]}
        filas = con.execute(
            """SELECT escrito, min(pagina) desde, max(pagina) hasta, count(*) n
               FROM segmento WHERE obra = ? AND capa='lacan' AND escrito IS NOT NULL
               GROUP BY escrito ORDER BY desde""", (obra,)).fetchall()
        return {"tipo": "escrito", "partes": [
            {"escrito": f["escrito"], "desde": f["desde"], "hasta": f["hasta"],
             "etiqueta": f["escrito"], "n": f["n"]} for f in filas]}
    finally:
        con.close()


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass                                  # sin ruido en la ventana negra

    def _responder(self, cuerpo, tipo="application/json; charset=utf-8"):
        datos = cuerpo if isinstance(cuerpo, bytes) else cuerpo.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        u = urlparse(self.path)
        p = parse_qs(u.query)
        try:
            if u.path == "/":
                return self._responder(PAGINA, "text/html; charset=utf-8")
            if u.path == "/api/buscar":
                return self._responder(json.dumps(api_buscar(p), ensure_ascii=False))
            if u.path == "/api/contexto":
                return self._responder(json.dumps(api_contexto(p), ensure_ascii=False))
            if u.path == "/api/analisis":
                return self._responder(json.dumps(api_analisis(p), ensure_ascii=False))
            if u.path == "/api/pagina":
                img = render_pagina(p)
                if img is None:
                    self.send_error(404)
                    return
                return self._responder(img, "image/png")
            if u.path == "/manifest.json":
                return self._responder(json.dumps(MANIFIESTO, ensure_ascii=False),
                                       "application/manifest+json")
            if u.path.startswith("/estatico/"):
                ruta = os.path.normpath(os.path.join(RAIZ, u.path.lstrip("/")))
                if not ruta.startswith(os.path.join(RAIZ, "estatico"))                         or not os.path.exists(ruta):
                    self.send_error(404)
                    return
                with open(ruta, "rb") as fh:
                    return self._responder(fh.read(), "image/png")
            if u.path == "/api/partes":
                return self._responder(json.dumps(api_partes(p), ensure_ascii=False))
            if u.path == "/api/catalogo":
                return self._responder(json.dumps(api_catalogo(), ensure_ascii=False))
        except Exception as e:                                    # noqa: BLE001
            return self._responder(json.dumps({"error": str(e)}, ensure_ascii=False))
        self.send_error(404)


PAGINA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Lacancito</title>
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/estatico/icono-192.png">
<meta name="theme-color" content="#7a4b2a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Lacancito">
<style>
  :root{
    --tinta:#1a1a1a; --papel:#faf8f5; --tenue:#6b6560; --linea:#e0dad2;
    --marca:#fdf0a8; --acento:#7a4b2a; --alerta:#a3341f;
  }
  @media (prefers-color-scheme: dark){
    :root{ --tinta:#e8e4de; --papel:#16151a; --tenue:#948d85; --linea:#33313a;
           --marca:#5c4a12; --acento:#d3a26e; --alerta:#e8846b; }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--papel);color:var(--tinta);
    font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
    display:flex;flex-direction:column;min-height:100vh}
  header{padding:20px;border-bottom:1px solid var(--linea);
    position:sticky;top:0;background:var(--papel);z-index:5}
  .caja{max-width:900px;margin:0 auto}
  .titulo{display:flex;align-items:baseline;gap:12px;margin-bottom:12px}
  h1{margin:0;font:600 19px/1 system-ui;letter-spacing:.02em}
  .titulo .sub{color:var(--tenue);font-size:14px;flex:1}
  #idioma{border:1px solid var(--linea);background:none;color:var(--tenue);
    border-radius:6px;padding:5px 11px;cursor:pointer;font-size:13px}
  #idioma:hover{color:var(--acento);border-color:var(--acento)}
  form{display:flex;gap:8px;flex-wrap:wrap}
  #q{flex:1 1 340px;min-width:0;padding:12px 14px;font-size:17px;
    border:1px solid var(--linea);border-radius:8px;background:var(--papel);
    color:var(--tinta)}
  #q:focus{outline:2px solid var(--acento);outline-offset:-1px}
  button.ir{padding:12px 22px;font-size:16px;border:0;border-radius:8px;
    background:var(--acento);color:#fff;cursor:pointer}
  .opciones{display:flex;gap:18px;flex-wrap:wrap;align-items:center;
    margin-top:12px;font-size:14px;color:var(--tenue)}
  .modos{display:flex;gap:2px;background:var(--linea);padding:2px;border-radius:8px}
  .modos label{padding:6px 13px;border-radius:6px;cursor:pointer;color:var(--tinta)}
  /* invisible pero enfocable: con display:none no se llega con el teclado */
  .modos input{position:absolute;opacity:0;width:0;height:0}
  .modos input:focus-visible + span{outline:2px solid var(--acento)}
  .modos input:checked + span{background:var(--papel);border-radius:6px;
    padding:6px 13px;margin:-6px -13px;display:inline-block;font-weight:600}
  select{padding:6px 8px;border:1px solid var(--linea);border-radius:6px;
    background:var(--papel);color:var(--tinta);max-width:280px}
  main{max-width:900px;margin:0 auto;padding:20px;width:100%;flex:1}
  .estado{color:var(--tenue);font-size:14px;margin-bottom:18px}
  .ayuda{color:var(--tenue);font-size:14px;line-height:1.7;
    border-left:3px solid var(--linea);padding-left:16px;margin-top:26px}
  .ayuda code{background:var(--linea);padding:1px 5px;border-radius:4px;
    font-size:13px}
  article{padding:16px 0;border-bottom:1px solid var(--linea)}
  .ref{font-size:13px;color:var(--acento);font-weight:600;letter-spacing:.01em}
  .ref .edic{color:var(--tenue);font-weight:400}
  .pasaje{margin:8px 0 10px;font:17px/1.65 Georgia,"Times New Roman",serif}
  mark{background:var(--marca);color:inherit;padding:1px 2px;border-radius:2px}
  .acciones{display:flex;gap:14px;font-size:13px;flex-wrap:wrap}
  .acciones button,.acciones a{background:none;border:0;color:var(--tenue);
    cursor:pointer;padding:0;font-size:13px;text-decoration:underline}
  .acciones button:hover,.acciones a:hover{color:var(--acento)}
  .contexto{margin:10px 0 0;padding:12px 16px;background:var(--linea);
    border-radius:8px;font:15px/1.6 Georgia,serif}
  .contexto p{margin:0 0 10px} .contexto p:last-child{margin:0}
  .contexto .foco{font-weight:600}
  textarea.reporte{width:100%;border:1px solid var(--acento);resize:vertical}
  .apa{margin:10px 0 0;padding:12px 16px;background:var(--linea);
    border-radius:8px;font:13px/1.6 ui-monospace,Consolas,monospace;
    white-space:pre-wrap;word-break:break-word}
  article.dudosa .pasaje{color:var(--alerta)}
  .aviso-dudosa{font-size:12px;color:var(--alerta);margin:6px 0 8px;
    border-left:3px solid var(--alerta);padding-left:10px}
  .fam{display:inline-block;font-size:11px;letter-spacing:.04em;
    text-transform:uppercase;color:var(--tenue);border:1px solid var(--linea);
    border-radius:99px;padding:1px 9px;margin-left:8px;vertical-align:1px}
  .apoyo{margin-top:12px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  .apoyo a{display:inline-block;border:1px solid var(--acento);color:var(--acento);
    border-radius:8px;padding:6px 14px;text-decoration:none;font-size:13px}
  .apoyo a:hover{background:var(--acento);color:var(--papel)}
  #linea{display:flex;align-items:flex-end;gap:2px;height:52px;margin:-6px 0 20px}
  #linea .anio{flex:1;background:var(--acento);opacity:.55;border-radius:2px 2px 0 0;
    min-height:2px;cursor:pointer;position:relative}
  #linea .anio:hover{opacity:1}
  #linea .anio span{position:absolute;bottom:-15px;left:50%;transform:translateX(-50%);
    font-size:9px;color:var(--tenue);white-space:nowrap}
  .bloque{margin:22px 0}
  .bloque h3{font:600 13px/1.4 system-ui;margin:0 0 6px;color:var(--tenue);
    text-transform:uppercase;letter-spacing:.04em}
  svg.graf{width:100%;height:auto;color:var(--tinta)}
  .resumen{padding:10px 0;border-bottom:1px solid var(--linea)}
  .resumen .pto{display:inline-block;width:10px;height:10px;border-radius:50%;
    margin-right:8px;vertical-align:0}
  .resumen .menor{font-size:12px;color:var(--tenue)}
  .resumen .datos{display:flex;gap:18px;flex-wrap:wrap;margin-top:6px;
    font-size:13px;color:var(--tenue)}
  .nota-analisis{font-size:13px;color:var(--tenue);line-height:1.7;
    border-left:3px solid var(--linea);padding-left:16px;margin-top:24px}
  .original{margin-top:10px}
  .original img{max-width:100%;border:1px solid var(--linea);border-radius:6px}
  .barra{display:flex;align-items:center;gap:12px;padding:5px 0;font-size:14px}
  .barra .nom{flex:0 0 320px;overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap}
  .barra .val{flex:0 0 56px;text-align:right;color:var(--tenue)}
  .barra .bar{height:11px;background:var(--acento);border-radius:3px;opacity:.75}
  footer{border-top:1px solid var(--linea);padding:20px;margin-top:30px;
    font-size:13px;color:var(--tenue)}
  footer a{color:var(--acento)}
  footer .autor{color:var(--tinta);font-weight:600}
  /* ── Teléfono ──────────────────────────────────────────────────────────
     Dos cosas cambian en pantalla chica. Los filtros se pliegan detrás de un
     botón: son cinco desplegables que ocupaban media pantalla antes de que se
     viera un solo resultado. Y todo lo que se toca pasa a medir 44 px de alto,
     que es el mínimo para un dedo; a 15 px se erraba siempre. */
  #filtros{display:none;border:1px solid var(--linea);background:none;
    color:var(--tenue);border-radius:8px;padding:0 14px;height:44px;font-size:14px}
  @media (max-width:620px){
    header{padding:14px}
    main{padding:14px}
    #filtros{display:block;margin-top:10px;width:100%}
    .opciones{display:none}
    .opciones.abierto{display:flex;flex-direction:column;align-items:stretch;gap:12px}
    .opciones label{display:flex;align-items:center;gap:8px}
    .opciones select{flex:1;max-width:none;height:44px;font-size:15px}
    .modos{width:100%}
    .modos label{flex:1;text-align:center;padding:10px 4px;font-size:13px}
    .modos input:checked + span{padding:10px 4px;margin:-10px -4px;display:block}
    #q{font-size:16px;height:48px}          /* 16px evita que el iPhone haga zoom */
    button.ir{height:48px}
    .acciones{gap:0;flex-direction:column;align-items:stretch;margin-top:4px}
    .acciones button,.acciones a{min-height:44px;display:flex;align-items:center;
      text-decoration:none;border-top:1px solid var(--linea);font-size:15px}
    .pasaje{font-size:16px}
    svg.graf{min-height:110px}
    .barra .nom{flex-basis:120px}
    .resumen .datos{gap:10px 14px}
  }
</style></head><body>
<header><div class="caja">
  <div class="titulo">
    <h1>Lacancito</h1><span class="sub" id="t-sub"></span>
    <button id="idioma" type="button"></button>
  </div>
  <form id="f">
    <input id="q" autocomplete="off" autofocus>
    <button class="ir" type="submit" id="t-buscar"></button>
  </form>
  <button id="filtros" type="button"></button>
  <div class="opciones">
    <div class="modos">
      <label><input type="radio" name="modo" value="exacta" checked><span id="t-m1"></span></label>
      <label><input type="radio" name="modo" value="sonido"><span id="t-m2"></span></label>
      <label><input type="radio" name="modo" value="cerca"><span id="t-m4"></span></label>
      <label><input type="radio" name="modo" value="contar"><span id="t-m3"></span></label>
    </div>
    <label><span id="t-en"></span> <select id="obra"></select></label>
    <label><select id="familia"></select></label>
    <label><select id="parte"></select></label>
    <label id="lab-dist" style="display:none"><span id="t-dist"></span>
      <select id="distancia">
        <option>5</option><option selected>10</option>
        <option>25</option><option>50</option></select></label>
    <label><select id="capa">
      <option value="lacan"></option><option value="editor"></option>
      <option value="nota"></option><option value="todas"></option>
    </select></label>
  </div>
</div></header>
<main>
  <div class="estado" id="estado"></div>
  <div id="linea"></div>
  <div id="salida"></div>
  <div class="ayuda" id="ayuda"></div>
</main>
<footer><div class="caja">
  <span id="t-hecha"></span>
  <span class="autor">Waldo Karakas Garcilaso</span> ·
  <a href="https://lance.tiiny.site/" target="_blank" rel="noopener noreferrer">lance.tiiny.site</a> ·
  <a href="https://www.instagram.com/waldokg.psa/" target="_blank" rel="noopener noreferrer">@waldokg.psa</a>
  <div id="t-aviso" style="margin-top:8px"></div>
  <div class="apoyo">
    <span id="t-apoyo"></span>
    <a href="https://link.mercadopago.com.ar/lacancitoapp" target="_blank"
       rel="noopener noreferrer">Mercado Pago</a>
    <a href="https://www.paypal.com/paypalme/waldokarakas" target="_blank"
       rel="noopener noreferrer">PayPal</a>
  </div>
</div></footer>
<script>
const $ = s => document.querySelector(s);
const esc = t => String(t).replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const marcar = t => esc(t).replace(/»»/g,'<mark>').replace(/««/g,'</mark>');

/* ---------------------------------------------------------------- idiomas */
const T = {
 es:{ otro:'English', sub:'buscador de citas de Lacan', buscar:'Buscar',
   ph:'Escribí lo que buscás…', m1:'Texto exacto', m2:'Por cómo suena',
   m3:'Contar', m4:'Palabras cerca', en:'en', todas:'todas las obras',
   filtros:'Filtros',
   dist:'a menos de', palabras:'palabras',
   verPag:'ver la página original',
   cargando:'cargando…',
   aparic:'apariciones', sinFecha:'sin fecha', primera:'primera', ultima:'última',
   picoRel:'pico relativo', picoAbs:'pico absoluto', enObras:'en obras',
   gini:'concentración', fragmentos:'fragmentos',
   gRel:'Frecuencia relativa — apariciones por cada 10.000 palabras del año',
   gAbs:'Frecuencia absoluta — apariciones por año',
   gAcum:'Acumulado — cuándo irrumpe y cuándo se estanca',
   gObra:'Reparto por obra',
   notaRel:'La frecuencia relativa es la que importa para comparar años: en '+
     '1967 Lacan habló mucho más que en 1953, así que el conteo en bruto '+
     'favorece siempre a los años cargados. La concentración va de 0 (repartido '+
     'parejo entre las obras) a 1 (todo en una sola), y se calcula sobre tasas '+
     'por obra, no sobre conteos: sobre conteos mediría también el tamaño de '+
     'cada volumen. Se cuentan ocurrencias reales, no fragmentos que la '+
     'contienen: un pasaje que dice la palabra tres veces cuenta tres. Escribí '+
     'varios términos separados por coma para superponerlos.',
   gsem:'Seminarios', gesc:'Escritos',
   capas:['sólo lo que dijo Lacan','notas del transcriptor','notas al pie','todo'],
   ctx:'ver alrededor', ocultar:'ocultar', cita:'ver la cita completa',
   copiado:'copiado', copiar:'copiar la cita', trad:'traducir en DeepL ↗',
   sesion:'clase', suena:'suena', resultados:'resultados',
   muestran:n=>'(se muestran los primeros '+n+')', sinres:'sin resultados.',
   buscando:'buscando…', grupos:'grupos', docTrab:'doc. de trabajo',
   docTrabLargo:'documento de trabajo inédito', aprox:'aprox.',
   enTexto:'En el texto:', partioDe:'Establecido a partir de:',
   gotr:'Otros textos', todasFam:'todas las familias',
   todasPartes:{clase:'todas las clases', escrito:'todos los escritos',
                pieza:'todas las piezas'},
   clase:'clase', frag:'frag.', reportar:'avisar de un error',
   reportado:'copiado: pegalo donde puedas avisar',
   reportarManual:'copialo del cuadro de abajo',
   apoyo:'¿Te sirvió? Podés invitarme un café:',
   dudosa:'Transcripción no confiable. Puede venir de un facsímil manuscrito o '+
     'de un OCR pobre: verificá contra el original antes de citar. Si ves un '+
     'error, avisá.',
   en_libro:'En', clase_del:'clase del', hecha:'Hecha por',
   aviso:'Todo funciona en esta computadora. Lo único que sale a internet es '+
     'el enlace al traductor, y sólo cuando lo apretás.',
   ayuda:'<b>Texto exacto</b> — varias palabras se buscan como frase entera. '+
     'No hace falta poner los acentos.<br><b>Por cómo suena</b> — encuentra los '+
     'equívocos. Buscá <code>nom du père</code> y aparece también '+
     '<code>les non-dupes errent</code>, que suena igual y no se escribe igual. '+
     'Trae de más: es a propósito.<br><b>Contar</b> — cuántas veces aparece una '+
     'palabra y en qué obras o años, sin mostrar texto.<br>'+
     'El número de página siempre viene con la edición de la que salió. En los '+
     'seminarios es la del documento de trabajo, no la de Seuil ni la de Paidós.'},
 en:{ otro:'Español', sub:'a search engine for Lacan quotations', buscar:'Search',
   ph:'Type what you are looking for…', m1:'Exact text', m2:'By sound',
   m3:'Count', m4:'Words near', en:'in', todas:'all works',
   filtros:'Filters',
   dist:'within', palabras:'words',
   verPag:'show original page',
   cargando:'loading…',
   aparic:'occurrences', sinFecha:'undated', primera:'first', ultima:'last',
   picoRel:'relative peak', picoAbs:'absolute peak', enObras:'in works',
   gini:'concentration', fragmentos:'fragments',
   gRel:'Relative frequency — occurrences per 10,000 words of that year',
   gAbs:'Absolute frequency — occurrences per year',
   gAcum:'Cumulative — when it breaks in and when it plateaus',
   gObra:'Distribution across works',
   notaRel:'Relative frequency is what matters when comparing years: Lacan '+
     'spoke far more in 1967 than in 1953, so raw counts always favour the busy '+
     'years. Concentration runs from 0 (spread evenly across works) to 1 (all '+
     'in one), computed on per-work rates rather than raw counts, which would '+
     'also measure volume size. Real occurrences are counted, not fragments '+
     'containing the term. Type several terms separated by commas to overlay.',
   gsem:'Seminars', gesc:'Écrits',
   capas:["only Lacan's words",'transcriber notes','footnotes','everything'],
   ctx:'show surrounding text', ocultar:'hide', cita:'show full reference',
   copiado:'copied', copiar:'copy reference', trad:'translate on DeepL ↗',
   sesion:'session', suena:'sounds like', resultados:'results',
   muestran:n=>'(showing the first '+n+')', sinres:'no results.',
   buscando:'searching…', grupos:'groups', docTrab:'working doc.',
   docTrabLargo:'unpublished working document', aprox:'approx.',
   enTexto:'In-text:', partioDe:'Established from:',
   gotr:'Other texts', todasFam:'all families',
   todasPartes:{clase:'all sessions', escrito:'all écrits',
                pieza:'all pieces'},
   clase:'session', frag:'frag.', reportar:'report an error',
   reportado:'copied: paste it wherever you can report it',
   reportarManual:'copy it from the box below',
   apoyo:'Found it useful? You can buy me a coffee:',
   dudosa:'Unreliable transcription. It may come from a handwritten facsimile '+
     'or from poor OCR: check against the original before quoting. If you spot '+
     'an error, let me know.',
   en_libro:'In', clase_del:'session of', hecha:'Built by',
   aviso:'Everything runs on this computer. The only thing that leaves it is '+
     'the translator link, and only when you click it.',
   ayuda:'<b>Exact text</b> — several words are searched as a whole phrase. '+
     'Accents are optional.<br><b>By sound</b> — finds the equivocations. Search '+
     '<code>nom du père</code> and <code>les non-dupes errent</code> also shows '+
     'up: same sound, different spelling. It over-returns on purpose.<br>'+
     '<b>Count</b> — how often a word appears and in which works or years, '+
     'without showing text.<br>The page number always comes with the edition it '+
     'belongs to. For the seminars that is the working document, not Seuil.'}
};
let L = localStorage.getItem('lacancito.idioma') || 'es';
let CAT = {obras:[], fuentes:{}};
let HAY_PDF = false;

function pintarIdioma(){
  const t = T[L];
  document.documentElement.lang = L;
  $('#idioma').textContent = t.otro;
  $('#t-sub').textContent = t.sub;
  $('#t-buscar').textContent = t.buscar;
  $('#q').placeholder = t.ph;
  $('#t-m1').textContent = t.m1; $('#t-m2').textContent = t.m2;
  $('#t-m3').textContent = t.m3; $('#t-en').textContent = t.en;
  $('#t-m4').textContent = t.m4; $('#t-dist').textContent = t.dist;
  $('#filtros').textContent = ($('.opciones').classList.contains('abierto')
                               ? '✕ ' : '≡ ') + t.filtros;
  $('#ayuda').innerHTML = t.ayuda;
  pintarFamilias();
  $('#t-hecha').textContent = t.hecha + ' ';
  $('#t-aviso').textContent = t.aviso;
  $('#t-apoyo').textContent = t.apoyo;
  [...$('#capa').options].forEach((o,i)=> o.textContent = t.capas[i]);
  pintarObras();
}

function pintarFamilias(){
  const t = T[L], sel = $('#familia'), antes = sel.value;
  sel.innerHTML = '<option value="">'+esc(t.todasFam)+'</option>';
  (CAT.familias||[]).forEach(f=>{
    const op = document.createElement('option');
    op.value = f; op.textContent = f.toLowerCase();
    sel.appendChild(op);
  });
  sel.value = antes;
}

async function pintarPartes(){
  const t = T[L], sel = $('#parte'), obra = $('#obra').value;
  sel.innerHTML = '';
  if(!obra){ sel.style.display='none'; return; }
  const d = await (await fetch('/api/partes?obra='+encodeURIComponent(obra)
        + '&familia='+encodeURIComponent($('#familia').value))).json();
  if(!d.partes.length){ sel.style.display='none'; return; }
  sel.style.display='';
  sel.innerHTML = '<option value="">'
    + esc(t.todasPartes[d.tipo] || '—') + '</option>';
  d.partes.forEach(pt=>{
    const op = document.createElement('option');
    op.value = JSON.stringify({escrito:pt.escrito||'', fecha:pt.fecha||'',
                               sesion:pt.sesion||''});
    let et;
    if(d.tipo === 'clase') et = t.clase+' '+pt.sesion+' · '+fechaCorta(pt.fecha);
    else if(d.tipo === 'escrito') et = pt.etiqueta+'  (pp. '+pt.desde+'–'+pt.hasta+')';
    else et = fechaCorta(pt.fecha)+' · '+pt.etiqueta;
    op.textContent = et.length > 78 ? et.slice(0,76)+'…' : et;
    op.title = et + '  —  ' + pt.n + ' ' + t.frag;
    sel.appendChild(op);
  });
}

function pintarObras(){
  const t = T[L], sel = $('#obra'), antes = sel.value;
  sel.innerHTML = '<option value="">'+esc(t.todas)+'</option>';
  const grupos = {sem:t.gsem, esc:t.gesc, otr:t.gotr};
  for(const g of ['sem','esc','otr']){
    const items = CAT.obras.filter(o=>o.grupo===g);
    if(!items.length) continue;
    const og = document.createElement('optgroup'); og.label = grupos[g];
    items.forEach(o=>{
      const op = document.createElement('option');
      op.value = o.obra; op.textContent = nombreObra(o.obra);
      og.appendChild(op);
    });
    sel.appendChild(og);
  }
  sel.value = antes;
  pintarPartes();
}

/* En español van los títulos que puso el autor; en inglés, el título original
   en francés que trae la edición, que es como se los cita afuera. */
function nombreObra(obra){
  const f = CAT.fuentes[obra];
  if(L === 'es' || !f) return obra;
  const m = obra.match(/Seminario\s+(\d+b?)/);
  if(m && f.numero) return 'Seminar ' + f.numero.replace('Livre ','') + ' — ' + f.titulo;
  return f.titulo || obra;
}

/* ------------------------------------------------------------------ citas */
function fechaCorta(iso){
  if(!iso) return '';
  const [a,m,d] = iso.split('-');
  return L === 'es' ? d+'/'+m+'/'+a : iso;
}

function referencia(r){
  const t = T[L], f = CAT.fuentes[r.obra] || {};
  let p = [nombreObra(r.obra)];
  if(r.escrito) p.push('«'+r.escrito+'»');
  if(r.sesion_n) p.push(t.sesion+' '+r.sesion_n+' · '+fechaCorta(r.sesion_fecha));
  else if(r.sesion_fecha) p.push(fechaCorta(r.sesion_fecha));
  let pag = 'p. '+r.pagina;
  if(r.aprox) pag += ' ('+t.aprox+')';
  p.push(pag);
  const edic = f.paginacion === 'documento de trabajo' ? t.docTrab : f.paginacion;
  return {texto: p.join(' · '), edicion: edic ? ' — '+edic : ''};
}

/* Referencia en APA. Los seminarios y las conferencias no tienen editorial ni
   año de publicación: son documentos de trabajo publicados en un sitio, y así
   se citan. Los dos volúmenes de Écrits sí son libros y llevan editorial. */
function apa(r){
  const t = T[L], f = CAT.fuentes[r.obra];
  if(!f) return '';
  const anios = f.anios || 's.f.';
  let ref, loc = [];
  if(r.sesion_fecha) loc.push(t.clase_del+' '+fechaCorta(r.sesion_fecha));
  loc.push('p. '+r.pagina);

  if(f.tipo === 'libro'){
    const dentro = r.escrito ? r.escrito+'. '+t.en_libro+' ' : '';
    ref = 'Lacan, J. ('+anios+'). '+dentro+f.titulo+'. '+f.editorial+'.';
  } else if(f.tipo === 'elp'){
    /* Acá lo que se cita es la pieza, no el volumen: lleva su propia fecha y
       su propio título, y el volumen queda como el lugar donde está. */
    ref = 'Lacan, J. ('+(r.sesion_fecha || anios)+'). '+(r.escrito || f.titulo)
        + '. '+t.en_libro+' '+f.titulo+' ['+(f.version||'').toLowerCase()+']. '
        + f.sitio+'.';
    loc = ['p. '+r.pagina];
  } else {
    const num = f.numero ? 'Le séminaire, '+f.numero+': ' : '';
    const ver = f.version ? ' ('+f.version+')' : '';
    ref = 'Lacan, J. ('+anios+'). '+num+f.titulo+ver+'. '
        + (f.sitio ? f.sitio+'. ' : '') + (f.url || '');
  }
  // en «Otros» el año que va en la cita es el de la pieza, no el del volumen
  const anioTexto = (f.tipo === 'elp' && r.sesion_fecha)
      ? r.sesion_fecha.slice(0, 4) : anios;
  return ref.trim()
       + '\n\n' + t.enTexto + ' (Lacan, '+anioTexto+', '+loc.join(', ')+')'
       + (f.fuente_declarada ? '\n\n' + t.partioDe + ' ' + f.fuente_declarada : '');
}

function enlaceDeepl(texto, idioma){
  const desde = idioma || 'fr';
  const hacia = desde === 'es' ? 'fr' : (L === 'en' ? 'en' : 'es');
  return 'https://www.deepl.com/'+(L==='en'?'en':'es')+'/translator#'
       + desde+'/'+hacia+'/'+encodeURIComponent(texto);
}

function tarjeta(r){
  const t = T[L], ref = referencia(r);
  const a = document.createElement('article');
  a.dataset.r = JSON.stringify(r);
  if(r.dudosa) a.className = 'dudosa';
  const chapa = r.familia ? '<span class="fam">'+esc(r.familia.toLowerCase())+'</span>' : '';
  a.innerHTML =
      '<div class="ref">'+esc(ref.texto)+'<span class="edic">'+esc(ref.edicion)+'</span>'+chapa+'</div>'
    + (r.dudosa ? '<div class="aviso-dudosa">⚠ '+esc(t.dudosa)+'</div>' : '')
    + '<div class="pasaje">'+marcar(r.pasaje)+'</div>'
    + '<div class="acciones">'
    + '<button data-ctx="'+r.id+'">'+esc(t.ctx)+'</button>'
    + '<button data-apa="1">'+esc(t.cita)+'</button>'
    + '<a href="'+esc(enlaceDeepl(r.texto, r.idioma))+'" target="_blank"'
    + ' rel="noopener noreferrer">'+esc(t.trad)+'</a>'
    + (HAY_PDF ? '<button data-pag="1">'+esc(t.verPag)+'</button>' : '')
    + '<button data-err="1">'+esc(t.reportar)+'</button>'
    + '</div>';
  return a;
}

/* --------------------------------------------------------------- eventos */
$('#idioma').addEventListener('click', ()=>{
  L = (L === 'es') ? 'en' : 'es';
  localStorage.setItem('lacancito.idioma', L);
  pintarIdioma();
  if($('#q').value.trim()) $('#f').requestSubmit();
});

$('#salida').addEventListener('click', async ev => {
  const b = ev.target.closest('button'); if(!b) return;
  const art = b.closest('article'), t = T[L];
  if(b.dataset.pag){
    const ya = art.querySelector('.original');
    if(ya){ ya.remove(); b.textContent = t.verPag; return; }
    const r = JSON.parse(art.dataset.r);
    b.textContent = t.cargando;
    const div = document.createElement('div'); div.className = 'original';
    div.innerHTML = '<img loading="lazy" src="/api/pagina?id='+r.id+'">';
    art.appendChild(div); b.textContent = t.ocultar;
    return;
  }
  if(b.dataset.err){
    /* No hay servidor a donde mandarlo: la app corre en la máquina de cada
       uno. Se arma el reporte y se copia, para pegarlo donde se pueda avisar. */
    const r = JSON.parse(art.dataset.r);
    const ref = referencia(r);
    const txt = `LACANCITO — posible error de transcripción
fragmento: ${r.id}
referencia: ${ref.texto}${ref.edicion}
${r.dudosa ? 'marcado como transcripción dudosa' : ''}

texto tal como aparece:
${r.texto}

qué está mal: `;
    /* El reporte se muestra siempre en un cuadro seleccionable, y además se
       intenta copiar. El portapapeles del navegador falla en algunos casos y
       no conviene que el aviso dependa de que ande. */
    const ya = art.querySelector('.reporte');
    if(ya){ ya.remove(); b.textContent = t.reportar; return; }
    const caja = document.createElement('textarea');
    caja.className = 'apa reporte'; caja.rows = 8; caja.value = txt;
    art.appendChild(caja); caja.focus(); caja.select();
    try { await navigator.clipboard.writeText(txt); b.textContent = t.reportado; }
    catch(e) { b.textContent = t.reportarManual; }
    return;
  }
  if(b.dataset.apa){
    const ya = art.querySelector('.apa');
    if(ya){ ya.remove(); b.textContent = t.cita; return; }
    const r = JSON.parse(art.dataset.r);
    const div = document.createElement('div'); div.className='apa';
    div.textContent = apa(r);
    const cop = document.createElement('button');
    cop.textContent = t.copiar; cop.style.cssText='display:block;margin-top:8px';
    cop.onclick = async () => { await navigator.clipboard.writeText(apa(r));
                                cop.textContent = t.copiado; };
    div.appendChild(cop); art.appendChild(div); b.textContent = t.ocultar;
  }
  if(b.dataset.ctx){
    const ya = art.querySelector('.contexto');
    if(ya){ ya.remove(); b.textContent = t.ctx; return; }
    const d = await (await fetch('/api/contexto?id='+b.dataset.ctx)).json();
    const div = document.createElement('div'); div.className='contexto';
      div.innerHTML = d.vecinos.map(v=>'<p'+(v.foco?' class="foco"':'')+'>[p. '
        +v.pagina+'] '+esc(v.texto)+'</p>').join('');
    art.appendChild(div); b.textContent = t.ocultar;
  }
});

$('#filtros').addEventListener('click', () => {
  const abierto = $('.opciones').classList.toggle('abierto');
  $('#filtros').textContent = (abierto ? '✕ ' : '≡ ') + T[L].filtros;
});

$('#q').addEventListener('keydown', e => {
  if(e.key === 'Enter'){ e.preventDefault(); $('#f').requestSubmit(); }
});
function parteQS(){
  const v = $('#parte').value;
  if(!v) return '';
  const p = JSON.parse(v);
  return Object.entries(p).filter(([k,x])=>x)
    .map(([k,x])=>'&'+k+'='+encodeURIComponent(x)).join('');
}

$('#obra').addEventListener('change', async ()=>{
  await pintarPartes();
  if($('#q').value.trim()) $('#f').requestSubmit();
});
$('#parte').addEventListener('change', ()=>{ if($('#q').value.trim()) $('#f').requestSubmit(); });
$('#familia').addEventListener('change', async ()=>{
  await pintarPartes();
  if($('#q').value.trim()) $('#f').requestSubmit();
});
document.querySelectorAll('input[name=modo]').forEach(r =>
  r.addEventListener('change', ()=>{
    $('#lab-dist').style.display =
      document.querySelector('input[name=modo]:checked').value === 'cerca' ? '' : 'none';
    if($('#q').value.trim()) $('#f').requestSubmit();
  }));
$('#distancia').addEventListener('change', ()=>{ if($('#q').value.trim()) $('#f').requestSubmit(); });

const COLORES = ['var(--acento)', '#3d7ea6', '#7a8b3d'];

function curva(serie, campo, ancho, alto, color){
  /* Una polilínea simple en SVG. No hace falta librería: son 50 puntos. */
  const vals = serie.map(x => x[campo] || 0);
  const max = Math.max(...vals, 1);
  const paso = ancho / Math.max(1, serie.length - 1);
  const pts = vals.map((v,i)=> (i*paso).toFixed(1)+','+(alto - alto*v/max).toFixed(1));
  return '<polyline fill="none" stroke="'+color+'" stroke-width="2" points="'
       + pts.join(' ') + '"/>';
}

function grafico(titulo, terminos, campo, alto){
  const ancho = 760, pad = 34;
  const anios = terminos[0].serie.map(x=>x.anio);
  const max = Math.max(...terminos.flatMap(t=>t.serie.map(x=>x[campo]||0)), 1);
  let svg = '<svg viewBox="0 0 '+(ancho+pad*2)+' '+(alto+34)+'" class="graf">';
  svg += '<g transform="translate('+pad+',8)">';
  terminos.forEach((t,i)=>{ svg += curva(t.serie, campo, ancho, alto, COLORES[i]); });
  // eje: una marca cada cinco años
  anios.forEach((a,i)=>{
    if(+a % 5) return;
    const x = (i*ancho/Math.max(1,anios.length-1)).toFixed(1);
    svg += '<line x1="'+x+'" y1="'+alto+'" x2="'+x+'" y2="'+(alto+4)+'" stroke="currentColor" opacity=".3"/>'
        +  '<text x="'+x+'" y="'+(alto+17)+'" text-anchor="middle" font-size="10" fill="currentColor" opacity=".55">'+a+'</text>';
  });
  svg += '<text x="0" y="-1" font-size="10" fill="currentColor" opacity=".55">'+esc(String(max))+'</text>';
  svg += '</g></svg>';
  return '<div class="bloque"><h3>'+esc(titulo)+'</h3>'+svg+'</div>';
}

async function pintarAnalisis(q){
  const t = T[L];
  $('#estado').textContent = t.buscando;
  const d = await (await fetch('/api/analisis?q='+encodeURIComponent(q)
        +'&capa='+$('#capa').value)).json();
  if(d.error || !d.terminos || !d.terminos.length){
    $('#estado').textContent = t.sinres; return; }
  const T3 = d.terminos;
  $('#estado').textContent = T3.map(x=>'«'+x.termino+'» '+x.total.toLocaleString()).join('  ·  ')
    + (T3.length > 1 ? '' : '');
  const cont = $('#salida'); cont.innerHTML = '';

  // resumen por término
  T3.forEach((x,i)=>{
    const sinf = x.sin_fecha ? ' · '+x.sin_fecha+' '+t.sinFecha : '';
    cont.insertAdjacentHTML('beforeend',
      '<div class="resumen"><span class="pto" style="background:'+COLORES[i]+'"></span>'
      + '<b>'+esc(x.termino)+'</b> — '+x.total.toLocaleString()+' '+t.aparic
      + ' <span class="menor">'+t.en+' '+x.fragmentos.toLocaleString()+' '+t.fragmentos+'</span>'+sinf
      + '<div class="datos">'
      + '<span>'+t.primera+' <b>'+x.primera+'</b></span>'
      + '<span>'+t.ultima+' <b>'+x.ultima+'</b></span>'
      + '<span>'+t.picoRel+' <b>'+x.pico_rel+'</b></span>'
      + '<span>'+t.picoAbs+' <b>'+x.pico_abs+'</b></span>'
      + '<span>'+t.enObras+' <b>'+x.obras_con+'/'+x.obras_total+'</b></span>'
      + '<span>'+t.gini+' <b>'+x.gini+'</b></span>'
      + '</div></div>');
  });

  cont.insertAdjacentHTML('beforeend', grafico(t.gRel, T3, 'rel', 120));
  cont.insertAdjacentHTML('beforeend', grafico(t.gAbs, T3, 'n', 90));
  cont.insertAdjacentHTML('beforeend', grafico(t.gAcum, T3, 'acum', 90));

  // reparto por obra, del primer término
  const po = T3[0].por_obra, maxo = Math.max(...po.map(o=>o.n), 1);
  let html = '<div class="bloque"><h3>'+esc(t.gObra)+' — «'+esc(T3[0].termino)+'»</h3>';
  po.forEach(o=>{
    html += '<div class="barra"><span class="nom">'+esc(nombreObra(o.obra))+'</span>'
         +  '<span class="val">'+o.n+'</span>'
         +  '<span class="bar" style="width:'+Math.max(2, 60*o.n/maxo)+'%"></span></div>';
  });
  cont.insertAdjacentHTML('beforeend', html + '</div>');
  cont.insertAdjacentHTML('beforeend', '<div class="nota-analisis">'+t.notaRel+'</div>');
}

function pintarLinea(linea){
  const cont = $('#linea'); cont.innerHTML = '';
  if(!linea || linea.length < 2) return;
  /* Se dibujan todos los años del recorrido, incluso los de cero, porque el
     hueco también dice algo: cuándo Lacan dejó de usar una palabra. */
  const desde = +linea[0].anio, hasta = +linea[linea.length-1].anio;
  const mapa = {}; linea.forEach(x=>mapa[x.anio] = x.n);
  const max = Math.max(...linea.map(x=>x.n));
  for(let a = desde; a <= hasta; a++){
    const n = mapa[a] || 0;
    const b = document.createElement('div'); b.className = 'anio';
    b.style.height = (n ? Math.max(6, 100*n/max) : 2) + '%';
    b.title = a + ': ' + n;
    if(n && (a % 5 === 0 || n === max)) b.innerHTML = '<span>'+a+'</span>';
    cont.appendChild(b);
  }
}

$('#f').addEventListener('submit', async ev => {
  ev.preventDefault();
  const t = T[L], q = $('#q').value.trim(); if(!q) return;
  const modo = document.querySelector('input[name=modo]:checked').value;
  $('#ayuda').style.display = 'none';
  $('#estado').textContent = t.buscando; $('#salida').innerHTML = '';
  $('#linea').innerHTML = '';
  const u = '/api/buscar?q='+encodeURIComponent(q)+'&modo='+modo
          + '&obra='+encodeURIComponent($('#obra').value)
          + '&capa='+$('#capa').value
          + '&familia='+encodeURIComponent($('#familia').value)
          + parteQS() + '&distancia='+$('#distancia').value + '&limite=30';
  const d = await (await fetch(u)).json();
  if(d.error){ $('#estado').textContent = 'Error: '+d.error; return; }

  if(d.modo === 'contar'){ await pintarAnalisis(q); return; }
  pintarLinea(d.linea);
  const suena = d.suena ? ' — '+t.suena+' /'+d.suena+'/' : '';
  const dem = d.total > d.resultados.length ? ' '+t.muestran(d.resultados.length) : '';
  $('#estado').textContent = d.resultados.length
    ? '«'+q+'»'+suena+' — '+d.total+' '+t.resultados+dem
    : '«'+q+'» — '+t.sinres;
  d.resultados.forEach(r=>$('#salida').appendChild(tarjeta(r)));
});

fetch('/api/catalogo').then(r=>r.json()).then(d=>{
  CAT = d; HAY_PDF = !!d.hay_pdf;
  pintarIdioma();
});
</script></body></html>
"""


def puerto_libre():
    for p in PUERTOS:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    sys.exit("No encontré un puerto libre. Cerrá otras copias de Lacancito.")


def main():
    global DB_ACTUAL
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB,
                    help="qué base usar; con la pública no se muestra texto")
    args = ap.parse_args()
    DB_ACTUAL = args.db
    bajar_base_si_falta(DB_ACTUAL)
    if not os.path.exists(DB_ACTUAL):
        # Es lo primero que ve quien acaba de bajar el repositorio: la base
        # no viene incluida y hay que armarla con los libros propios.
        sys.exit(f"""
No encuentro la base de datos en:
  {DB_ACTUAL}

{AYUDA_SIN_BASE}""")

    print("Preparando el buscador…")
    con = conexion()
    asegurar_indice(con)
    total = con.execute("SELECT count(*) FROM segmento").fetchone()[0]
    con.close()

    # En un servidor, el puerto y la dirección los impone el proveedor; en una
    # computadora se busca uno libre y se escucha sólo desde adentro.
    alojado = bool(os.environ.get("PORT"))
    puerto = int(os.environ["PORT"]) if alojado else puerto_libre()
    host = "0.0.0.0" if alojado else "127.0.0.1"
    url = f"http://localhost:{puerto}/"
    print(f"\n  Lacancito está andando: {url}")
    print(f"  {total:,} fragmentos listos para buscar.")
    print("\n  Se abre solo en el navegador. Si no, copiá esa dirección.")
    print("  Para cerrarlo, cerrá esta ventana.\n")

    if not alojado:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        ThreadingHTTPServer((host, puerto), Manejador).serve_forever()
    except KeyboardInterrupt:
        print("Cerrado.")


if __name__ == "__main__":
    main()
