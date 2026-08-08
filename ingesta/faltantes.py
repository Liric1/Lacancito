# -*- coding: utf-8 -*-
"""
Dice qué parte de un texto candidato YA está en la base, antes de cargarlo.

Sin esto, cargar la carpeta de textos sueltos o el «Lacan completo» duplicaría
casi todo: la mayoría de esos archivos son los mismos escritos y seminarios que
ya tenemos, en otro formato. Un buscador con el mismo pasaje tres veces es peor
que uno con el pasaje una vez.

Cómo mide: toma muestras del candidato repartidas de punta a punta, las
normaliza (sin acentos, sin puntuación, sin mayúsculas) y busca cada una en el
texto ya cargado, también normalizado. El porcentaje de muestras encontradas es
la cobertura. Alto = ya lo tenemos; bajo = es material nuevo.

Es una medición, no una decisión: imprime los números y el criterio queda a la
vista para discutirlo.

    python ingesta/faltantes.py "C:\\...\\lacan textos" --db datos/lacancito.db
"""
import argparse
import glob
import os
import re
import sqlite3
import sys
import unicodedata

MUESTRAS = 200         # cuántos trozos se prueban por archivo
# El largo del trozo decide qué se está midiendo, y conviene tenerlo claro.
# Con trozos largos (90 car.) un texto que YA tenemos pero escaneado con OCR da
# cobertura baja, porque una errata cada pocas palabras rompe todas las
# coincidencias largas: parece material nuevo y no lo es. Con trozos cortos
# (30 car.) las erratas se saltean y queda a la vista la diferencia real:
#   texto ya cargado, con OCR sucio  -> sube mucho al acortar (6% -> 40%)
#   texto que de verdad falta        -> sigue en casi cero (0% -> 3%)
LARGO = 30


def normalizar(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def leer(ruta):
    if ruta.lower().endswith(".txt"):
        crudo = open(ruta, "rb").read()
        for cod in ("utf-8", "cp1252", "latin-1"):
            try:
                return crudo.decode(cod)
            except UnicodeDecodeError:
                continue
        return crudo.decode("latin-1", "replace")
    if ruta.lower().endswith(".pdf"):
        import pymupdf
        d = pymupdf.open(ruta)
        t = "\n".join(d[n].get_text() for n in range(d.page_count))
        d.close()
        return t
    return ""


def cobertura(texto, corpus):
    """Qué proporción de las muestras del texto ya está en el corpus."""
    n = normalizar(texto)
    if len(n) < LARGO * 2:
        return None, 0
    paso = max(1, (len(n) - LARGO) // MUESTRAS)
    trozos = [n[i:i + LARGO] for i in range(0, len(n) - LARGO, paso)][:MUESTRAS]
    hallados = sum(1 for t in trozos if t in corpus)
    return hallados / len(trozos), len(n)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta")
    ap.add_argument("--db", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "datos", "lacancito.db"))
    ap.add_argument("--patron", default="*.txt")
    ap.add_argument("--umbral", type=float, default=0.5,
                    help="por encima de esto se considera ya cargado")
    args = ap.parse_args()

    print("Leyendo lo que ya está cargado…")
    con = sqlite3.connect(args.db)
    corpus = " ".join(normalizar(r[0]) for r in con.execute(
        "SELECT texto FROM segmento WHERE capa = 'lacan'"))
    con.close()
    print(f"  {len(corpus):,} caracteres normalizados de referencia\n")

    archivos = sorted(glob.glob(os.path.join(args.carpeta, args.patron)))
    print(f"{'ARCHIVO':<52}{'TAMAÑO':>10}{'YA ESTÁ':>10}   ESTADO")
    print("-" * 96)
    nuevos = []
    for a in archivos:
        try:
            cob, largo = cobertura(leer(a), corpus)
        except Exception as e:                                    # noqa: BLE001
            print(f"{os.path.basename(a)[:50]:<52}{'':>10}{'':>10}   !! {e}")
            continue
        if cob is None:
            print(f"{os.path.basename(a)[:50]:<52}{'':>10}{'':>10}   (muy corto)")
            continue
        estado = "ya cargado" if cob >= args.umbral else "► FALTA"
        if cob < args.umbral:
            nuevos.append((a, cob, largo))
        print(f"{os.path.basename(a)[:50]:<52}{largo:>10,}{cob:>9.0%}   {estado}")

    print("-" * 96)
    print(f"\n{len(nuevos)} archivo(s) por debajo del {args.umbral:.0%}: material nuevo.")
    for a, cob, largo in nuevos:
        print(f"   {os.path.basename(a):<54}{cob:>5.0%} ya está, {largo:>9,} car.")


if __name__ == "__main__":
    main()
