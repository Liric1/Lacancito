# -*- coding: utf-8 -*-
"""Esquema unico de la base y guardado. Lo comparten todos los ingestores."""
import os
import sqlite3

CAMPOS = [
    "autor", "obra", "escrito", "version", "idioma", "capa", "sesion_n",
    "sesion_fecha", "pagina", "pagina_confianza", "pagina_pdf", "orden",
    "texto", "archivo", "familia", "confianza",
]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS segmento (
    id               INTEGER PRIMARY KEY,
    autor            TEXT NOT NULL,
    obra             TEXT NOT NULL,   -- Ecrits / Seminario 20 — Aun
    escrito          TEXT,            -- articulo dentro de la obra, si aplica
    version          TEXT NOT NULL,   -- de que establecimiento del texto viene
    idioma           TEXT NOT NULL,
    capa             TEXT NOT NULL,   -- lacan | editor | nota
    sesion_n         INTEGER,
    sesion_fecha     TEXT,
    pagina           INTEGER,
    pagina_confianza TEXT,            -- exacta | verificada | estimada
    pagina_pdf       INTEGER,
    orden            INTEGER,
    texto            TEXT NOT NULL,
    fonetica         TEXT,            -- como suena; ver ingesta/fonetica.py
    familia          TEXT,            -- cartas, conferencias, entrevistas…
    confianza        TEXT,            -- alta | dudosa (calidad de la transcripcion)
    archivo          TEXT NOT NULL
);
"""

INDICES = """
CREATE INDEX IF NOT EXISTS ix_obra    ON segmento(obra, sesion_n, pagina, orden);
CREATE INDEX IF NOT EXISTS ix_escrito ON segmento(obra, escrito, pagina, orden);
CREATE INDEX IF NOT EXISTS ix_fecha   ON segmento(sesion_fecha);
CREATE INDEX IF NOT EXISTS ix_capa    ON segmento(capa);
CREATE INDEX IF NOT EXISTS ix_familia ON segmento(familia);
"""


def preparar(con):
    """Crea la tabla, le agrega las columnas que falten si viene de una version
    anterior, y recien entonces crea los indices (un indice sobre una columna
    que todavia no existe falla)."""
    con.executescript(ESQUEMA)
    existentes = {f[1] for f in con.execute("PRAGMA table_info(segmento)")}
    for campo, tipo in (("escrito", "TEXT"), ("pagina_confianza", "TEXT"),
                        ("fonetica", "TEXT"), ("familia", "TEXT"),
                        ("confianza", "TEXT")):
        if campo not in existentes:
            con.execute(f"ALTER TABLE segmento ADD COLUMN {campo} {tipo}")
    con.executescript(INDICES)
    # si cambio el contenido, el indice de busqueda quedo viejo: que se rehaga
    tablas = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "meta" in tablas:
        con.execute("DELETE FROM meta WHERE clave='indexados'")


def guardar(segmentos, ruta_db):
    """Inserta los segmentos, reemplazando lo que ya hubiera de la misma obra."""
    if not segmentos:
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(ruta_db)), exist_ok=True)
    con = sqlite3.connect(ruta_db)
    preparar(con)
    con.execute("DELETE FROM segmento WHERE obra = ?", (segmentos[0]["obra"],))
    con.executemany(
        f"INSERT INTO segmento ({', '.join(CAMPOS)}) "
        f"VALUES ({', '.join(':' + c for c in CAMPOS)})",
        [{c: s.get(c) for c in CAMPOS} for s in segmentos])
    con.commit()
    con.close()
    return len(segmentos)
