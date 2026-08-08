# -*- coding: utf-8 -*-
"""
Carga el catálogo «Otros»: lo que está en el assemblage chronologique y no en
los seminarios ni en los dos volúmenes de Écrits.

Son conferencias, entrevistas, cartas, intervenciones, casos clínicos y notas.
La lista de qué cargar y con qué familia sale de datos/otros_corregido.json,
que es la lista revisada a mano.

Dos cosas que este ingestor marca y conviene entender:

CONFIANZA DE LA TRANSCRIPCIÓN. Algunas piezas del volumen no son texto sino
facsímiles: la página del «Pneumatique à Pierre Soury» es la foto de una nota
manuscrita, no una transcripción. Otras vienen de un OCR pobre. Un fragmento se
marca «dudosa» cuando tiene demasiadas palabras de una o dos letras —la firma
de un OCR que perdió caracteres— o cuando la pieza entera devuelve muy poco
texto para las páginas que ocupa. En la app esos fragmentos salen en rojo, para
que quien los lea sepa que puede haber un error y avise.

IDIOMA. El volumen no es todo francés: hay piezas en español («Conversación con
Jacques Lacan», «El fenómeno lacaniano») y en inglés («Some reflections on the
Ego»). Se detecta por palabras frecuentes, porque de eso depende el enlace al
traductor y, más adelante, la búsqueda por sonido.

    python ingesta/ingestar_otros.py "...\\Lacan completo.pdf"
"""
import argparse
import collections
import json
import os
import re
import sys

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from esquema import guardar  # noqa: E402

DESFASE = 1              # folio impreso = índice del PDF + 1
ZONA_CABECERA = 34       # franja de arriba: fecha y titulillo
ZONA_PIE = 40            # franja de abajo: número de página
OBJETIVO_FRAGMENTO = 600
MIN_CAR_POR_PAGINA = 350  # menos que esto en una pieza: probablemente facsímil
UMBRAL_CORTAS = 0.48      # proporción de palabras de 1-2 letras que ya es sospechosa

OBRA = "Otros"
VERSION = "Pour une recherche : assemblage chronologique"

FRECUENTES = {
    "fr": {"le", "la", "les", "de", "des", "du", "et", "que", "qui", "dans",
           "pour", "pas", "ce", "il", "est", "une", "un", "en", "sur", "je"},
    "es": {"el", "la", "los", "las", "de", "del", "y", "que", "en", "por",
           "con", "no", "es", "una", "un", "para", "se", "su", "lo", "como"},
    "en": {"the", "of", "and", "to", "in", "that", "is", "it", "for", "as",
           "with", "was", "on", "be", "this", "which", "not", "by", "at", "from"},
}


def idioma_de(texto):
    pal = re.findall(r"[a-záéíóúàâçèêëîïôùûü]+", texto.lower())[:600]
    if len(pal) < 30:
        return "fr"
    cuenta = {k: sum(1 for p in pal if p in v) for k, v in FRECUENTES.items()}
    return max(cuenta, key=cuenta.get)


def proporcion_cortas(texto):
    tok = re.findall(r"[A-Za-zÀ-ÿ']+", texto)
    if len(tok) < 20:
        return None
    return sum(1 for x in tok if len(x.strip("'")) <= 2) / len(tok)


def limpiar(t):
    t = t.replace("\xad", "")
    t = re.sub(r"(\w)-\s+(?=[a-zà-öø-ÿ])", r"\1", t)
    t = re.sub(r"\s+([.,])", r"\1", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def fragmentar(texto, objetivo=OBJETIVO_FRAGMENTO):
    texto = texto.strip()
    if not texto:
        return []
    piezas, actual = [], ""
    for frase in re.split(r"(?<=[.!?…])\s+", texto):
        if actual and len(actual) + len(frase) + 1 > objetivo:
            piezas.append(actual.strip())
            actual = frase
        else:
            actual = f"{actual} {frase}".strip()
    if actual:
        piezas.append(actual.strip())
    return piezas


def texto_de_pagina(pg):
    """El cuerpo, sin el titulillo de arriba ni el número de página de abajo."""
    alto = pg.rect.height
    lineas = []
    for b in pg.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for l in b["lines"]:
            y = l["bbox"][1]
            if y < ZONA_CABECERA or y > alto - ZONA_PIE:
                continue
            t = "".join(s["text"] for s in l["spans"])
            if t.strip():
                lineas.append((round(y, 1), l["bbox"][0], t))
    lineas.sort(key=lambda x: (round(x[0] / 6), x[1]))
    return " ".join(t for _, _, t in lineas)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--lista", default=os.path.join(base, "datos",
                                                    "otros_corregido.json"))
    ap.add_argument("--db", default=os.path.join(base, "datos", "lacancito.db"))
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()

    piezas = json.load(open(args.lista, encoding="utf-8"))
    doc = pymupdf.open(args.pdf)
    archivo = os.path.basename(args.pdf)

    segmentos, sin_texto, dudosas = [], [], []
    idiomas = collections.Counter()
    for i, p in enumerate(piezas):
        ini = p["pagina"] - DESFASE
        pags = range(ini, min(ini + p["paginas"], doc.page_count))
        crudo = " ".join(texto_de_pagina(doc[n]) for n in pags)
        texto = limpiar(crudo)

        # una pieza que da muy poco texto para lo que ocupa suele ser facsímil
        densidad = len(texto) / max(1, p["paginas"])
        idi = idioma_de(texto)
        idiomas[idi] += 1
        if len(texto) < 80:
            sin_texto.append(p)
            continue

        flojo = densidad < MIN_CAR_POR_PAGINA
        for k, frag in enumerate(fragmentar(texto), start=1):
            pc = proporcion_cortas(frag)
            dudoso = flojo or (pc is not None and pc >= UMBRAL_CORTAS)
            segmentos.append({
                "archivo": archivo, "autor": "Jacques Lacan", "obra": OBRA,
                "escrito": p["titulo"], "version": VERSION, "idioma": idi,
                "capa": "lacan", "sesion_fecha": p["fecha"],
                "pagina": p["pagina"], "pagina_confianza": "exacta",
                "pagina_pdf": ini + 1, "orden": k, "texto": frag,
                "familia": p["familia"],
                "confianza": "dudosa" if dudoso else "alta",
            })
        if flojo:
            dudosas.append((p, round(densidad)))
        if i % 40 == 0:
            print(f"   {i}/{len(piezas)}", end="\r", flush=True)
    doc.close()

    alta = sum(1 for s in segmentos if s["confianza"] == "alta")
    print(f"\n\nPiezas cargadas : {len(piezas) - len(sin_texto)} de {len(piezas)}")
    print(f"Fragmentos      : {len(segmentos):,} "
          f"({alta:,} de confianza alta, {len(segmentos)-alta:,} dudosos)")
    print(f"Caracteres      : {sum(len(s['texto']) for s in segmentos):,}")
    print(f"Idiomas         : {dict(idiomas)}")

    if sin_texto:
        print(f"\n!! {len(sin_texto)} piezas sin texto extraíble "
              f"(seguramente facsímiles de manuscritos):")
        for p in sin_texto[:10]:
            print(f"     {p['fecha']:<12} p.{p['pagina']:<7} {p['titulo'][:60]}")
        if len(sin_texto) > 10:
            print(f"     … y {len(sin_texto)-10} más")

    if dudosas:
        print(f"\n{len(dudosas)} piezas con poco texto para su extensión "
              f"(quedan marcadas en rojo):")
        for p, d in sorted(dudosas, key=lambda x: x[1])[:8]:
            print(f"     {d:>4} car/pág  {p['fecha']:<12} {p['titulo'][:56]}")

    if args.preview:
        print("\n" + "=" * 78)
        for s in segmentos[:2]:
            print(f"\n[{s['escrito']} · {s['sesion_fecha']} · p.{s['pagina']} "
                  f"· {s['familia']} · {s['confianza']}]")
            print("  " + s["texto"][:340])
    else:
        print(f"\nGuardados {guardar(segmentos, args.db):,} fragmentos.")


if __name__ == "__main__":
    main()
