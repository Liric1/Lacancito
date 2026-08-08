# -*- coding: utf-8 -*-
"""
Saca la lista definitiva de lo que falta del «assemblage chronologique».

El sumario ya dijo qué piezas hay (ver sumario_assemblage.py). Pero clasificar
por el título no alcanza: nuestros escritos vienen del OCR y tienen los títulos
deformados, así que varias piezas que SÍ tenemos se colaban como si faltaran.

Acá se compara el texto, no el título. De cada pieza se leen unas páginas
salteadas, se normalizan y se busca cada trozo en lo ya cargado. Si aparece
casi todo, ya la tenemos. Si no aparece nada, falta.

Produce dos archivos:
    datos/otros_faltantes.json  para el ingestor
    datos/otros_faltantes.txt   para leer y corregir a mano

    python ingesta/lista_otros.py "...\\Lacan completo.pdf"
"""
import argparse
import collections
import json
import os
import re
import sqlite3
import sys
import unicodedata

import pymupdf

DESFASE = 1           # folio impreso = índice de página del PDF + 1
PAGS_MUESTRA = 3      # cuántas páginas se leen de cada pieza
TROZO = 30            # largo del trozo comparado (ver faltantes.py)
UMBRAL = 0.25         # por encima de esto, la pieza ya está cargada


def normalizar(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def cobertura(texto, corpus):
    n = normalizar(texto)
    if len(n) < TROZO * 4:
        return None
    paso = max(1, (len(n) - TROZO) // 60)
    tr = [n[i:i + TROZO] for i in range(0, len(n) - TROZO, paso)][:60]
    return sum(1 for t in tr if t in corpus) / len(tr)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--sumario", default=os.path.join(base, "datos",
                                                      "sumario_assemblage.json"))
    ap.add_argument("--db", default=os.path.join(base, "datos", "lacancito.db"))
    ap.add_argument("--salida", default=os.path.join(base, "datos", "otros_faltantes"))
    args = ap.parse_args()

    entradas = json.load(open(args.sumario, encoding="utf-8"))
    doc = pymupdf.open(args.pdf)

    # cada pieza va desde su página hasta donde empieza la siguiente
    conpag = [e for e in entradas if e.get("pagina")]
    for i, e in enumerate(conpag):
        sig = conpag[i + 1]["pagina"] if i + 1 < len(conpag) else doc.page_count
        e["hasta"] = max(e["pagina"], sig - 1)

    print("Leyendo lo ya cargado…")
    con = sqlite3.connect(args.db)
    corpus = " ".join(normalizar(r[0]) for r in con.execute(
        "SELECT texto FROM segmento WHERE capa = 'lacan'"))
    con.close()
    print(f"  {len(corpus):,} caracteres de referencia\n")

    otros = [e for e in conpag if e["clase"] == "otros"]
    print(f"Midiendo {len(otros)} piezas…")
    faltan, ya, cortas = [], [], []
    for i, e in enumerate(otros):
        ini, fin = e["pagina"] - DESFASE, e["hasta"] - DESFASE
        pags = list(range(ini, min(fin + 1, doc.page_count)))
        if not pags:
            cortas.append(e)
            continue
        paso = max(1, len(pags) // PAGS_MUESTRA)
        elegidas = pags[::paso][:PAGS_MUESTRA]
        texto = "\n".join(doc[p].get_text() for p in elegidas if 0 <= p < doc.page_count)
        cob = cobertura(texto, corpus)
        e["paginas"] = e["hasta"] - e["pagina"] + 1
        e["cobertura"] = None if cob is None else round(cob, 3)
        if cob is None:
            cortas.append(e)
        elif cob >= UMBRAL:
            ya.append(e)
        else:
            faltan.append(e)
        if i % 50 == 0:
            print(f"   {i}/{len(otros)}", end="\r", flush=True)
    doc.close()

    print(f"\n\n  faltan de verdad : {len(faltan):>4} piezas, "
          f"{sum(e['paginas'] for e in faltan):>6,} páginas")
    print(f"  ya estaban       : {len(ya):>4} piezas "
          f"(el título no coincidía, el texto sí)")
    print(f"  sin texto legible: {len(cortas):>4} piezas")

    fam = collections.Counter(e["familia"] or "(sin clasificar)" for e in faltan)
    print("\nLo que falta, por familia:")
    for f, n in fam.most_common():
        pg = sum(e["paginas"] for e in faltan if (e["familia"] or "(sin clasificar)") == f)
        print(f"   {f:<46}{n:>4} piezas {pg:>6,} pág.")

    if ya:
        print("\nPiezas que el título daba por nuevas y en realidad ya estaban:")
        for e in sorted(ya, key=lambda x: -x["cobertura"])[:12]:
            print(f"   {e['cobertura']:>5.0%}  {e['fecha']:<12} {e['titulo'][:64]}")

    with open(args.salida + ".json", "w", encoding="utf-8") as fh:
        json.dump(faltan, fh, ensure_ascii=False, indent=1)
    with open(args.salida + ".txt", "w", encoding="utf-8") as fh:
        fh.write("PIEZAS DE «Pour une recherche : assemblage chronologique»\n")
        fh.write("que NO están todavía en Lacancito.\n\n")
        fh.write("La familia es una clasificación automática por el título. Si alguna\n")
        fh.write("está mal puesta, corregila: es la última columna.\n")
        fh.write("=" * 100 + "\n")
        for f, _ in fam.most_common():
            fh.write(f"\n\n### {f.upper()}\n\n")
            for e in sorted((x for x in faltan
                             if (x["familia"] or "(sin clasificar)") == f),
                            key=lambda x: x["fecha"]):
                fh.write(f"{e['fecha']:<12} p.{e['pagina']:<6} {e['paginas']:>4} pág.  "
                         f"{e['titulo']}\n")
    print(f"\nLista guardada en {args.salida}.txt y .json")


if __name__ == "__main__":
    main()
