# -*- coding: utf-8 -*-
"""
Inventario de «Pour une recherche : assemblage chronologique» (Lacan completo).

Ese PDF son ~11.300 páginas con todo Lacan puesto en orden de fecha. Buena
parte ya la tenemos —los seminarios y los dos volúmenes de Écrits— y volver a
cargarla sería duplicar. Lo que interesa es lo otro: conferencias, alocuciones,
notas, intervenciones sueltas que no están en ningún libro.

Para saber qué hay adentro no hace falta leer el texto completo: cada página
lleva en el encabezado la fecha y el título de la pieza a la que pertenece.
Leyendo sólo esa franja se arma el índice del volumen en unos minutos, y recién
después se decide qué cargar.

    python ingesta/inventario_assemblage.py "...\\Lacan completo.pdf"
"""
import argparse
import collections
import json
import os
import re
import sys
import unicodedata

import pymupdf

ALTO_CABECERA = 30      # puntos desde arriba: sólo el titulillo
RE_FECHA = re.compile(r"(1[89]\d{2})[-/](\d{1,2})[-/](\d{1,2})")


def sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def normalizar(s):
    s = sin_acentos(s).upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def leer_cabeceras(ruta):
    """Una pasada rápida: sólo la franja superior de cada página."""
    doc = pymupdf.open(ruta)
    total = doc.page_count
    salida = []
    for n in range(total):
        pg = doc[n]
        r = pymupdf.Rect(0, 0, pg.rect.width, ALTO_CABECERA)
        txt = re.sub(r"\s+", " ", pg.get_text(clip=r)).strip()
        salida.append(txt)
        if n % 1000 == 0:
            print(f"   {n:,} / {total:,}", end="\r", flush=True)
    doc.close()
    print(f"   {total:,} / {total:,}")
    return salida


def agrupar(cabeceras):
    """Junta páginas seguidas que comparten encabezado: cada grupo es una pieza."""
    piezas = []
    for i, cab in enumerate(cabeceras):
        m = RE_FECHA.search(cab)
        fecha = (f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                 if m else None)
        titulo = RE_FECHA.sub("", cab).strip(" -–—·:")
        clave = (fecha, normalizar(titulo))
        if piezas and piezas[-1]["clave"] == clave:
            piezas[-1]["hasta"] = i + 1
            piezas[-1]["paginas"] += 1
        else:
            piezas.append({"clave": clave, "fecha": fecha, "titulo": titulo,
                           "desde": i + 1, "hasta": i + 1, "paginas": 1})
    return piezas


def juntar_por_titulo(piezas):
    """Un seminario aparece como muchas piezas (una por clase). Se agrupan por
    título para ver el volumen real de cada obra."""
    por_titulo = collections.OrderedDict()
    for p in piezas:
        k = normalizar(p["titulo"]) or "(SIN TITULO)"
        d = por_titulo.setdefault(k, {"titulo": p["titulo"], "piezas": 0,
                                      "paginas": 0, "desde": None, "hasta": None,
                                      "fechas": []})
        d["piezas"] += 1
        d["paginas"] += p["paginas"]
        d["desde"] = p["desde"] if d["desde"] is None else min(d["desde"], p["desde"])
        d["hasta"] = max(d["hasta"] or 0, p["hasta"])
        if p["fecha"]:
            d["fechas"].append(p["fecha"])
    return por_titulo


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--salida", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "datos", "inventario_assemblage.json"))
    ap.add_argument("--minimo", type=int, default=1,
                    help="no listar las entradas con menos páginas que esto")
    args = ap.parse_args()

    print("Leyendo los encabezados…")
    cabeceras = leer_cabeceras(args.pdf)
    piezas = agrupar(cabeceras)
    porto = juntar_por_titulo(piezas)

    sin_cab = sum(1 for c in cabeceras if not c.strip())
    print(f"\n{len(cabeceras):,} páginas · {len(piezas):,} tramos · "
          f"{len(porto):,} títulos distintos · {sin_cab:,} páginas sin encabezado\n")

    print(f"{'TÍTULO':<58}{'PIEZAS':>7}{'PÁGS':>7}   RANGO DE FECHAS")
    print("-" * 100)
    for k, d in sorted(porto.items(), key=lambda x: -x[1]["paginas"]):
        if d["paginas"] < args.minimo:
            continue
        f = sorted(d["fechas"])
        rango = f"{f[0]} … {f[-1]}" if f else "(sin fecha)"
        print(f"{d['titulo'][:56]:<58}{d['piezas']:>7}{d['paginas']:>7}   {rango}")

    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump({"piezas": piezas,
                   "por_titulo": {k: v for k, v in porto.items()}},
                  fh, ensure_ascii=False, indent=1)
    print(f"\nInventario guardado en {args.salida}")


if __name__ == "__main__":
    main()
