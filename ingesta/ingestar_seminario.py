# -*- coding: utf-8 -*-
"""
Ingestor de seminarios de Lacan (PDF de trabajo).

No son la version Staferla: cada PDF declara sus propias fuentes en la
pagina 2. Ver ingesta/fuentes.py.

Convierte un PDF de seminario en filas de una tabla. Cada fila es un fragmento
de texto que lleva pegados sus datos de referencia: seminario, numero de sesion,
fecha de la sesion, pagina, y de que CAPA viene.

Las tres capas se distinguen por la tipografia del propio documento:
  lacan   -> cuerpo, Garamond 10 pt. Las palabras de Lacan.
  editor  -> cuerpo chico (7-8 pt). Comentarios del transcriptor, [Rires], etc.
             El propio documento avisa: "Ce qui s'inscrit entre crochets droits
             [ ] n'est pas de Jacques Lacan".
  nota    -> notas al pie.

Uso:
    python ingestar_seminario.py "S20 ENCORE.pdf" --obra "Seminario 20" --preview
    python ingestar_seminario.py "S20 ENCORE.pdf" --obra "Seminario 20" --db datos/lacancito.db
"""
import argparse
import os
import re
import sys
import unicodedata

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from esquema import guardar  # noqa: E402

# --- parametros de reconocimiento tipografico -------------------------------
TAM_CUERPO_MIN = 9.5     # >= esto es texto de Lacan
TAM_REF_MAX = 6.5        # <= esto son numeritos de llamada a nota: se descartan
ZONA_PIE = 90            # ultimos N puntos de alto de pagina: notas al pie
ZONA_FOLIO = 60          # ultimos N puntos: numero de pagina impreso
ZONA_CABECERA = 170      # primeros N puntos: posible encabezado de sesion
OBJETIVO_FRAGMENTO = 600  # caracteres por fragmento (se corta en fin de frase)

MESES = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10,
    "novembre": 11, "decembre": 12,
}
MOIS_RE = "|".join(MESES)
CABECERA_RE = re.compile(rf"^\s*(\d{{1,2}})\s+({MOIS_RE})\s+(\d{{4}})(?!\d)", re.I)
FOLIO_RE = re.compile(r"^\s*(\d{1,4})\s*$")


def sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def fecha_iso(dia, mes_txt, anio):
    return f"{int(anio):04d}-{MESES[sin_acentos(mes_txt).lower()]:02d}-{int(dia):02d}"


def limpiar(t):
    t = t.replace("­", "").replace(" ", " ")
    t = re.sub(r"(\w)-\s+(?=[a-zàâäéèêëîïôöùûüç])", r"\1", t)  # corte de palabra
    t = re.sub(r"\s+([.,])", r"\1", t)      # el frances si deja espacio ante ; : ! ?
    t = re.sub(r"([.,])(?=[^\s.,)\]»])", r"\1 ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def lineas_de_pagina(pagina):
    """Devuelve las lineas en orden de lectura, con su capa y posicion."""
    alto = pagina.rect.height
    salida = []
    for bloque in pagina.get_text("dict")["blocks"]:
        if bloque.get("type") != 0:
            continue
        for linea in bloque["lines"]:
            y0, x0 = linea["bbox"][1], linea["bbox"][0]
            completa = "".join(s["text"] for s in linea["spans"]).strip()
            trozos = {"lacan": [], "editor": [], "nota": [], "folio": []}
            if y0 >= alto - ZONA_FOLIO and FOLIO_RE.match(completa):
                trozos["folio"].append(completa)
                salida.append((round(y0, 1), x0, trozos))
                continue
            en_pie = y0 >= alto - ZONA_PIE
            fin_anterior = None
            saltado = False       # venimos de descartar un span: no pegar palabras
            for s in linea["spans"]:
                tam, txt = s["size"], s["text"]
                if not txt.strip() or (not en_pie and tam <= TAM_REF_MAX):
                    fin_anterior = s["bbox"][2]
                    saltado = True
                    continue      # espacio suelto, o llamada a nota al pie
                if en_pie:
                    capa = "nota"
                elif tam >= TAM_CUERPO_MIN:
                    capa = "lacan"
                else:
                    capa = "editor"
                # el PDF corta palabras en spans distintos y a veces se come el
                # espacio: lo reponemos si hay hueco o si descartamos algo en medio
                hueco = fin_anterior is not None and s["bbox"][0] - fin_anterior > 0.8
                if (hueco or saltado) and not txt.startswith(" "):
                    txt = " " + txt
                trozos[capa].append(txt)
                fin_anterior = s["bbox"][2]
                saltado = False
            salida.append((round(y0, 1), x0, trozos))
    # agrupamos por renglon visual (la y varia unas decimas dentro de un renglon)
    salida.sort(key=lambda t: (round(t[0] / 6), t[1]))
    return salida, alto


def fragmentar(texto, objetivo=OBJETIVO_FRAGMENTO):
    """Parte un texto largo en fragmentos que terminan en fin de frase."""
    texto = texto.strip()
    if not texto:
        return []
    frases = re.split(r"(?<=[.!?…])\s+", texto)
    fragmentos, actual = [], ""
    for f in frases:
        if actual and len(actual) + len(f) + 1 > objetivo:
            fragmentos.append(actual.strip())
            actual = f
        else:
            actual = f"{actual} {f}".strip()
    if actual:
        fragmentos.append(actual.strip())
    return fragmentos


FECHA_EN_FILA = re.compile(rf"(\d{{1,2}})\s+({MOIS_RE})\s*(\d{{4}})", re.I)


def normalizar_digitos(t):
    """Estos PDF escriben a veces la ele minuscula en lugar del uno: 'l962'."""
    return re.sub(r"\b[lO0-9]{2,4}\b",
                  lambda m: m.group(0).replace("l", "1").replace("O", "0"), t)


def sesiones_por_enlaces(doc):
    """La 'Table des seances' de la pagina 2 tiene un enlace interno por sesion,
    que apunta a la pagina exacta donde empieza. Es la fuente mas confiable:
    no depende de como este maquetado el encabezado dentro del texto.

    Devuelve {indice_de_pagina: fecha_iso}."""
    mapa = {}
    for n in range(min(4, doc.page_count)):
        for enlace in doc[n].get_links():
            destino = enlace.get("page")
            if destino is None or destino < 0 or destino <= n:
                continue
            # el rectangulo del enlace a veces cubre solo el dia y el mes;
            # lo ampliamos un poco para alcanzar el ano, pero no tanto como para
            # invadir la columna de al lado (algunas tablas van a dos columnas)
            r = pymupdf.Rect(enlace["from"])
            medio = (r.y0 + r.y1) / 2
            fila = doc[n].get_textbox(
                pymupdf.Rect(r.x0 - 60, medio - 3, r.x1 + 130, medio + 3))
            m = FECHA_EN_FILA.search(normalizar_digitos(sin_acentos(fila)))
            if m:
                mapa.setdefault(destino, fecha_iso(*m.groups()))
    return mapa


def ingestar(ruta_pdf, obra, autor="Jacques Lacan",
             version="Documento de trabajo inédito", idioma="fr"):
    doc = pymupdf.open(ruta_pdf)
    archivo = os.path.basename(ruta_pdf)
    por_enlace = sesiones_por_enlaces(doc)
    segmentos, sesiones = [], []
    sesion_n, sesion_fecha, folio = None, None, None

    for n in range(doc.page_count):
        lineas, alto = lineas_de_pagina(doc[n])
        capas = {"lacan": [], "editor": [], "nota": []}

        # 1) la tabla de sesiones dice que aca empieza una clase
        if n in por_enlace and por_enlace[n] != sesion_fecha:
            sesion_fecha = por_enlace[n]
            sesion_n = len(sesiones) + 1
            sesiones.append((sesion_n, sesion_fecha, n + 1))

        for y0, x0, trozos in lineas:
            if trozos["folio"]:
                m = FOLIO_RE.match("".join(trozos["folio"]).strip())
                if m:
                    folio = int(m.group(1))
            crudo = "".join(trozos["lacan"] + trozos["editor"])
            if y0 < ZONA_CABECERA:
                m = CABECERA_RE.match(sin_acentos(crudo).strip())
                if m:
                    # 2) encabezado impreso dentro del texto: nunca es cuerpo.
                    #    Si la tabla de sesiones no dijo nada, manda este.
                    iso = fecha_iso(*m.groups())
                    if not por_enlace and iso != sesion_fecha:
                        sesion_fecha = iso
                        sesion_n = len(sesiones) + 1
                        sesiones.append((sesion_n, iso, n + 1))
                    continue
            for capa in ("lacan", "editor", "nota"):
                if trozos[capa]:
                    capas[capa].append("".join(trozos[capa]))

        if sesion_fecha is None:
            continue                              # portada y tabla de sesiones

        for capa in ("lacan", "editor", "nota"):
            texto = limpiar(" ".join(capas[capa]))
            for i, frag in enumerate(fragmentar(texto), start=1):
                segmentos.append({
                    "archivo": archivo, "autor": autor, "obra": obra,
                    "version": version, "idioma": idioma, "capa": capa,
                    "sesion_n": sesion_n, "sesion_fecha": sesion_fecha,
                    "pagina": folio if folio is not None else n + 1,
                    "pagina_pdf": n + 1, "orden": i, "texto": frag,
                })

    doc.close()
    return sesiones, segmentos, set(por_enlace.values())


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--obra", default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()

    obra = args.obra or os.path.splitext(os.path.basename(args.pdf))[0]
    sesiones, segs, declaradas = ingestar(args.pdf, obra)

    por_capa = {}
    for s in segs:
        c = por_capa.setdefault(s["capa"], [0, 0])
        c[0] += 1
        c[1] += len(s["texto"])

    encontradas = {iso for _, iso, _ in sesiones}
    print(f"Obra      : {obra}")
    print(f"Sesiones  : {len(sesiones)} encontradas en el texto"
          f" / {len(declaradas)} declaradas en la tabla de sesiones")
    for n_ses, iso, pag in sesiones:
        aviso = "" if iso in declaradas else "   <- no figura en la tabla"
        print(f"   {n_ses:>2}. {iso}   (empieza en pag. {pag}){aviso}")
    faltan = sorted(set(declaradas) - encontradas)
    if faltan:
        print(f"   !! DECLARADAS PERO NO ENCONTRADAS: {', '.join(faltan)}")
    print("Fragmentos por capa:")
    for capa in ("lacan", "editor", "nota"):
        n, chars = por_capa.get(capa, [0, 0])
        print(f"   {capa:<7} {n:>6} fragmentos   {chars:>10,} caracteres")

    if args.preview:
        print("\n" + "=" * 78)
        muestra = [s for s in segs if s["capa"] == "lacan"]
        for s in muestra[:2] + muestra[len(muestra) // 2:len(muestra) // 2 + 2]:
            print(f"\n[{s['obra']} | sesion {s['sesion_n']} del {s['sesion_fecha']}"
                  f" | pag. {s['pagina']} | frag. {s['orden']} | capa {s['capa']}]")
            print("  " + s["texto"])

    if args.db:
        guardar(segs, args.db)
        print(f"\nGuardado en {args.db}")


if __name__ == "__main__":
    main()
