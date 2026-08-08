# -*- coding: utf-8 -*-
"""
Registra de qué edición viene cada obra, para poder citarla en serio.

Por qué hace falta: decir «Seminario 17, clase 1, p. 10» es engañoso. Esa
página 10 no existe en Paidós ni en Seuil: es la del documento de trabajo que
usamos. Quien vaya a buscarla no la va a encontrar. Cada número de página tiene
que venir con la edición de la que salió.

Los seminarios de esta carpeta son la versión Staferla. La portada no lo dice,
pero los documentos enlazan a staferla.free.fr para sus propias referencias
internas, que es la firma del compilador.

Además, cada PDF declara en su página 2 los materiales de los que se partió
—estenotipias del sitio de l'École lacanienne de psychanalyse, audios del sitio
de Patrick Valas, versiones Chollet o Tallandier, reprografías—, y son
distintos en cada seminario. Eso se guarda aparte y literal, porque también
hace a la cita: no es lo mismo un seminario establecido desde una estenotipia
que uno transcripto de un audio.

    python ingesta/fuentes.py --carpeta "...\\0LACAN" --db datos/lacancito.db
"""
import argparse
import os
import re
import sqlite3
import sys

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from esquema import preparar  # noqa: E402

ROMANOS = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII",
           8: "VIII", 9: "IX", 10: "X", 11: "XI", 12: "XII", 13: "XIII",
           14: "XIV", 15: "XV", 16: "XVI", 17: "XVII", 18: "XVIII", 19: "XIX",
           20: "XX", 21: "XXI", 22: "XXII", 23: "XXIII", 24: "XXIV",
           25: "XXV", 26: "XXVI", 27: "XXVII"}

RE_FUENTE = re.compile(
    r"pour sources? principales?\s*:(.{0,900}?)"
    r"(?:Le texte de ce|N\.B\.|Les référence|Table des|\(Contact\))", re.S | re.I)
RE_ANIOS = re.compile(r"\b(19[3-8]\d)\s*[-–]\s*(\d{2,4})\b")

# Los dos volúmenes publicados: acá la editorial y el año sí existen, y la
# página impresa es la de Seuil. Se cargan a mano porque son datos de tapa.
LIBROS = {
    "Écrits": dict(
        titulo="Écrits", anios="1966", editorial="Éditions du Seuil",
        lugar="Paris", paginacion="Seuil, 1966",
        fuente_declarada="Edición impresa, digitalizada con OCR."),
    "Autres écrits": dict(
        titulo="Autres écrits", anios="2001", editorial="Éditions du Seuil",
        lugar="Paris", paginacion="Seuil, 2001",
        fuente_declarada="Edición impresa, digitalizada con OCR. "
                         "Textos reunidos por Jacques-Alain Miller."),
}

# El catálogo «Otros»: lo que no está en ningún libro. Sale del assemblage
# chronologique, un documento de trabajo interno de la escuela, y se cita como
# tal: el volumen entero es la fuente, y cada pieza va con su fecha y su página.
OTROS = dict(
    titulo="Pour une recherche : assemblage chronologique",
    anios="1926–1981", tipo="elp",
    sitio="École lacanienne de psychanalyse",
    version="Documento de trabajo interno",
    paginacion="assemblage chronologique",
    fuente_declarada="Volumen que reúne en orden cronológico la obra de Lacan. "
                     "Buena parte del material no está publicado en libro.")

ESQUEMA_FUENTE = """
DROP TABLE IF EXISTS fuente;
CREATE TABLE fuente (
    obra              TEXT PRIMARY KEY,
    autor             TEXT NOT NULL,
    titulo            TEXT NOT NULL,   -- en el idioma original
    numero            TEXT,            -- Livre XVII, para los seminarios
    anios             TEXT,            -- 1969-1970
    tipo              TEXT NOT NULL,   -- libro | staferla | elp
    version           TEXT,            -- «Version Staferla»
    sitio             TEXT,            -- quién lo publica: Staferla, e.l.p.
    url               TEXT,
    editorial         TEXT,
    lugar             TEXT,
    fuente_declarada  TEXT,            -- literal, lo que dice el documento
    contacto          TEXT,
    paginacion        TEXT NOT NULL,   -- de qué edición es el número de página
    ruta              TEXT             -- dónde está el PDF, para ver el original
);
"""

# Los documentos de trabajo de esta carpeta se publican en el sitio de
# Staferla. No lo dicen en la portada, pero enlazan a staferla.free.fr para sus
# propias referencias internas, que es la firma del compilador. Las fuentes que
# declaran adentro —estenotipias de la école lacanienne de psychanalyse, audios
# de Patrick Valas, versiones Chollet o Tallandier— son los materiales de los
# que Staferla partió, y se guardan aparte porque también hacen a la cita.
STAFERLA = dict(version="Version Staferla", sitio="Staferla",
                url="http://staferla.free.fr", paginacion="Staferla")


def limpiar(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    # la portada corta las líneas después del apóstrofe: «L’ envers de / la
    # psychanalyse». Al unirlas queda un espacio que no va.
    return re.sub(r"([’'])\s+", r"\1", t)


def leer_pdf_seminario(ruta):
    """Saca de la portada y de la página 2 el título, los años y las fuentes."""
    doc = pymupdf.open(ruta)
    portada = doc[0].get_text()
    frente = "\n".join(doc[n].get_text() for n in range(min(3, doc.page_count)))
    contacto = None
    for n in range(min(3, doc.page_count)):
        for enlace in doc[n].get_links():
            if enlace.get("uri", "").startswith("mailto:"):
                contacto = enlace["uri"][7:]
    doc.close()

    # la portada es: LACAN / <título en una o más líneas> / <años>, más el
    # folio suelto de la página 1 y a veces el año pegado al final del título
    lineas = [l.strip() for l in portada.split("\n") if l.strip()]
    titulo = []
    for l in lineas:
        if re.fullmatch(r"LACAN", l, re.I) or re.fullmatch(r"[\d\W]+", l):
            continue                       # el «1» del folio, guiones sueltos
        if RE_ANIOS.search(l) or re.fullmatch(r"\d{4}\s*[-–]\s*\d{2,4}", l):
            break
        titulo.append(l)
    bruto = limpiar(" ".join(titulo))
    bruto = re.sub(r"\s*[\dl]{4}\s*[-–]?\s*[\dl]{0,4}\s*$", "", bruto)  # año al final
    bruto = re.sub(r"\s+([’'])", r"\1", bruto)         # « d ’objet » -> « d’objet »
    bruto = re.sub(r"([a-zà-ÿ])([A-ZÀ-Þ])", r"\1 \2", bruto)  # « LeDésir » -> « Le Désir »
    titulo = [bruto] if bruto else []
    m = RE_FUENTE.search(frente)
    a = RE_ANIOS.search(frente)
    return (limpiar(" ".join(titulo)) or None,
            f"{a.group(1)}–{a.group(2)}" if a else None,
            limpiar(m.group(1)) if m else None,
            contacto)


def numero_de_seminario(nombre_archivo):
    m = re.match(r"S\s*(\d+)(b?)", os.path.basename(nombre_archivo), re.I)
    if not m:
        return None, None
    n, bis = int(m.group(1)), m.group(2)
    return (f"{n}{bis}", ROMANOS.get(n, str(n)) + (" bis" if bis else ""))


def cargar_correcciones(ruta):
    """Mismo formato que datos/titulos.txt: obra :: detectado :: corregido.
    Sirve para arreglar a mano los títulos que la portada trae abreviados."""
    if not ruta or not os.path.exists(ruta):
        return {}
    corr = {}
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            p = [x.strip() for x in linea.split("::")]
            if len(p) == 3 and p[2]:
                corr[(p[0], p[1])] = p[2]
    return corr


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--carpeta", required=True)
    ap.add_argument("--raiz", default=None,
                    help="dónde buscar los PDF (por defecto, la carpeta madre)")
    ap.add_argument("--db", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "datos", "lacancito.db"))
    ap.add_argument("--correcciones", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "datos", "obras.txt"))
    ap.add_argument("--exportar", action="store_true",
                    help="volcar los títulos detectados al archivo de correcciones")
    args = ap.parse_args()
    corr = cargar_correcciones(args.correcciones)

    # dónde está físicamente cada PDF: hace falta para poder mostrar la página
    # original cuando alguien quiere ver un esquema o verificar una cita
    raiz = args.raiz or os.path.dirname(os.path.abspath(args.carpeta))
    rutas = {}
    for dirpath, _, files in os.walk(raiz):
        for f in files:
            if f.lower().endswith(".pdf"):
                rutas.setdefault(f, os.path.join(dirpath, f))

    con = sqlite3.connect(args.db)
    preparar(con)
    con.executescript(ESQUEMA_FUENTE)

    # qué obras hay en la base, y de qué archivo salió cada una
    obras = con.execute(
        "SELECT obra, archivo, count(*) FROM segmento GROUP BY obra").fetchall()
    filas, sin_datos, detectados = [], [], {}

    for obra, archivo, _ in obras:
        if obra == "Otros":
            d = OTROS
            filas.append((obra, "Jacques Lacan", d["titulo"], None, d["anios"],
                          d["tipo"], d["version"], d["sitio"], None, None, None,
                          d["fuente_declarada"], None, d["paginacion"],
                          rutas.get(archivo)))
            continue
        if obra in LIBROS:
            d = LIBROS[obra]
            filas.append((obra, "Jacques Lacan", d["titulo"], None, d["anios"],
                          "libro", None, None, None, d["editorial"], d["lugar"],
                          d["fuente_declarada"], None, d["paginacion"],
                          rutas.get(archivo)))
            continue
        ruta = os.path.join(args.carpeta, archivo)
        if not os.path.exists(ruta):
            sin_datos.append(obra)
            continue
        titulo, anios, fuente, contacto = leer_pdf_seminario(ruta)
        ruta = rutas.get(archivo, ruta)
        detectado = titulo or obra
        _, romano = numero_de_seminario(archivo)
        filas.append((obra, "Jacques Lacan", corr.get((obra, detectado), detectado),
                      f"Livre {romano}" if romano else None, anios,
                      "staferla", STAFERLA["version"], STAFERLA["sitio"],
                      STAFERLA["url"], None, None, fuente, contacto,
                      STAFERLA["paginacion"], ruta))
        detectados[obra] = detectado

    con.executemany("INSERT OR REPLACE INTO fuente VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    filas)

    # Algunos PDF no ponen los años en la portada. No hay que inventarlos: se
    # deducen de las fechas de clase que ya están cargadas.
    con.execute("""
        UPDATE fuente SET anios = (
            SELECT substr(min(s.sesion_fecha),1,4) || '–' || substr(max(s.sesion_fecha),1,4)
            FROM segmento s WHERE s.obra = fuente.obra AND s.sesion_fecha IS NOT NULL)
        WHERE anios IS NULL AND EXISTS (
            SELECT 1 FROM segmento s WHERE s.obra = fuente.obra
            AND s.sesion_fecha IS NOT NULL)""")
    # un seminario que empezó y terminó el mismo año se cita con un año solo
    con.execute("UPDATE fuente SET anios = substr(anios,1,4) WHERE anios LIKE"
                " '____–____' AND substr(anios,1,4) = substr(anios,6,4)")

    # La atribución vieja decía «Staferla» y era incorrecta: estos documentos no
    # son esa versión. Se corrige en los fragmentos ya cargados.
    n = con.execute(
        "UPDATE segmento SET version = 'Documento de trabajo inédito'"
        " WHERE version LIKE 'Staferla%'").rowcount
    if n:
        print(f"Corregidos {n:,} fragmentos que decían «Staferla».\n")
    con.commit()

    print(f"{len(filas)} obras registradas.\n")
    for f in con.execute("SELECT obra, numero, anios, tipo, paginacion,"
                         " substr(coalesce(fuente_declarada,''),1,58)"
                         " FROM fuente ORDER BY obra"):
        print(f"  {f[0][:40]:<42}{(f[1] or ''):<12}{(f[2] or '?'):<11}"
              f"{f[4]:<22}{f[5]}")
    faltan = con.execute(
        "SELECT count(*) FROM segmento s WHERE NOT EXISTS"
        " (SELECT 1 FROM fuente f WHERE f.obra = s.obra)").fetchone()[0]
    if faltan or sin_datos:
        print(f"\n!! {faltan} fragmentos sin edición registrada. Obras: {sin_datos}")

    huerfanas = [c for (o, c) in corr if detectados.get(o) != c]
    if huerfanas:
        print(f"\n!! {len(huerfanas)} corrección(es) de {args.correcciones} no se"
              f" aplicaron: su clave ya no coincide con ningún título detectado.")
        for c in huerfanas:
            print(f"     {c!r}")

    if args.exportar:
        with open(args.correcciones, "w", encoding="utf-8") as fh:
            fh.write("# Títulos de las obras, tal como los trae la portada del\n"
                     "# PDF. Corregí lo que va DESPUÉS del segundo :: y volvé a\n"
                     "# correr fuentes.py. No toques lo que va antes.\n\n")
            for obra in sorted(detectados):
                fh.write(f"{obra} :: {detectados[obra]} :: "
                         f"{corr.get((obra, detectados[obra]), detectados[obra])}\n")
        print(f"\nTítulos volcados en {args.correcciones}")
    con.close()


if __name__ == "__main__":
    main()
