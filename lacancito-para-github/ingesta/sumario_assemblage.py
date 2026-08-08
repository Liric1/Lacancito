# -*- coding: utf-8 -*-
"""
Lee el sumario del «assemblage chronologique» y arma el índice del volumen.

El volumen trae su propio sumario de 38 páginas, con una entrada por pieza:

    1966-02-16
    La place de la psychanalyse dans la médecine | p. 6809

Eso es mucho mejor que deducir el contenido de los titulillos de cada página,
que el OCR entrega rotos. Con el sumario quedan la fecha exacta, el título
completo y la página impresa donde empieza cada pieza.

Después clasifica cada entrada en tres montones:

    seminario   ya lo tenemos, viene de los PDF por seminario
    escrito     ya lo tenemos, está en Écrits o Autres écrits
    otros       conferencias, entrevistas, cartas, notas: esto es lo que falta

    python ingesta/sumario_assemblage.py "...\\Lacan completo.pdf"
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

PAG_SUMARIO = (6, 43)        # dónde está el sumario dentro del PDF
RE_ENTRADA = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2}(?:/\d{1,2})?)\s")
RE_PAGINA = re.compile(r"\|\s*p\.\s*(\d+)")


def sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def normalizar(s):
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ",
                                      sin_acentos(s).upper())).strip()


def leer_sumario(ruta, desde, hasta):
    doc = pymupdf.open(ruta)
    texto = "\n".join(doc[n].get_text() for n in range(desde - 1, hasta))
    doc.close()
    return re.sub(r"[ \t]+", " ", texto)


def parsear(texto):
    """Corta el sumario en entradas. Cada una arranca con su fecha."""
    cortes = [(m.start(), m) for m in RE_ENTRADA.finditer(texto)]
    entradas = []
    for i, (pos, m) in enumerate(cortes):
        fin = cortes[i + 1][0] if i + 1 < len(cortes) else len(texto)
        cuerpo = texto[m.end():fin]
        mp = RE_PAGINA.search(cuerpo)
        titulo = re.sub(r"\s+", " ", cuerpo[:mp.start()] if mp else cuerpo).strip()
        if not titulo:
            continue
        anio, mes, dia = m.group(1), int(m.group(2)), m.group(3).split("/")[0]
        entradas.append({
            "fecha": f"{anio}-{mes:02d}-{int(dia):02d}" if dia.isdigit() and int(dia) else f"{anio}-{mes:02d}",
            "anio": int(anio),
            "titulo": titulo,
            "pagina": int(mp.group(1)) if mp else None,
        })
    return entradas


# Cómo se reconoce cada montón. El orden importa: gana el primero que entra.
CLASES = [
    ("seminario", r"^SEMINAIRE\b|^SEMINARIO\b"),
    ("resumen", r"^RESUME DU SEMINAIRE"),
]

PATRONES = [
    ("Cartas y notas privadas",
     r"^LETTRE|^CARTE |PNEUMATIQUE|^NOTE A |^NOTE SUR|^BILLET|CORRESPONDANCE|^TELEGRAMME"),
    ("Entrevistas y conversaciones",
     r"ENTRETIEN|CONVERSACI|INTERVIEW|^DIALOGUE|RADIOPHONIE|TELEVISION|EMISSION|^PROPOS RECUEILLIS"),
    ("Casos y presentaciones clínicas",
     r"^AVEC |^UN CAS|PRESENTATION DE MALADE|^A PROPOS DU CAS|SYNDROME|DELIRE|PARALYSIE|PSYCHOSE HALLUCINATOIRE"),
    ("Intervenciones y discusiones",
     r"^INTERVENTION|^DISCUSSION|^REPONSE A|^A PROPOS|^REMARQUE|^COMPTE RENDU|^SUR L|^CONTRIBUTION"),
    ("Congresos y jornadas",
     r"CONGRES|COLLOQUE|SYMPOSIUM|JOURNEE|RENCONTRE|CONFERENCE DE PRESSE|SEMINAIRE DE CARACAS"),
    ("Conferencias y clases fuera del seminario",
     r"^CONFERENCE|^ALLOCUTION|^DISCOURS|^CAUSERIE|^EXPOSE|^LECON|^INTRODUCTION AU|^PLACE, ORIGINE"),
    ("Escuela: actas y política",
     r"ECOLE|E F P|FONDATION|DISSOLUTION|^PROPOSITION|SCILICET|ANNUAIRE|STATUT|^ACTE DE|^ADRESSE|^LETTRE DE DISSOLUTION"),
    ("Prefacios, prólogos y reseñas",
     r"^PREFACE|^AVANT PROPOS|^PRESENTATION|^AVIS|^POSTFACE|^PROLOGUE|^NOTE ITALIENNE"),
    ("Homenajes y necrológicas",
     r"HOMMAGE|IN MEMORIAM|^A LA MEMOIRE|NECROLOG"),
]


def clasificar(titulo):
    t = normalizar(titulo)
    for nombre, rx in CLASES:
        if re.search(rx, t):
            return nombre, None
    for nombre, rx in PATRONES:
        if re.search(rx, t):
            return "otros", nombre
    return "otros", None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--db", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "datos", "lacancito.db"))
    ap.add_argument("--salida", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "datos", "sumario_assemblage.json"))
    args = ap.parse_args()

    entradas = parsear(leer_sumario(args.pdf, *PAG_SUMARIO))
    print(f"{len(entradas):,} entradas en el sumario, "
          f"de {entradas[0]['fecha']} a {entradas[-1]['fecha']}\n")

    # los escritos que ya tenemos, para no volver a cargarlos
    con = sqlite3.connect(args.db)
    ya = {normalizar(r[0]) for r in con.execute(
        "SELECT DISTINCT escrito FROM segmento WHERE escrito IS NOT NULL")}
    con.close()

    cuenta = collections.Counter()
    familias = collections.Counter()
    for e in entradas:
        clase, familia = clasificar(e["titulo"])
        n = normalizar(e["titulo"])
        if clase == "otros" and any(n.startswith(x[:28]) or x.startswith(n[:28])
                                    for x in ya if len(x) > 12):
            clase, familia = "escrito", None
        e["clase"], e["familia"] = clase, familia
        cuenta[clase] += 1
        if clase == "otros":
            familias[familia or "(sin clasificar)"] += 1

    print("Qué hay en el volumen:")
    for c, n in cuenta.most_common():
        print(f"   {c:<12}{n:>5} entradas")
    print("\nDentro de «otros», por familia:")
    for f, n in familias.most_common():
        print(f"   {f:<46}{n:>5}")

    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump(entradas, fh, ensure_ascii=False, indent=1)
    print(f"\nÍndice guardado en {args.salida}")


if __name__ == "__main__":
    main()
