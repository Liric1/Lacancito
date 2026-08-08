# -*- coding: utf-8 -*-
"""
Calcula cómo suena cada fragmento y arma el índice de búsqueda por sonido.

Hay que correrlo una vez después de cada ingesta. Es idempotente: sólo procesa
los fragmentos que todavía no tienen su forma sonora calculada, salvo que se
pida --rehacer.

    python ingesta/indexar_fonetica.py --db datos/lacancito.db
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from esquema import preparar          # noqa: E402
from fonetica import fonetizar        # noqa: E402

# tokenize='trigram' permite buscar cualquier trozo de la cadena de fonemas,
# no sólo palabras enteras: es lo que hace falta cuando el índice no tiene
# espacios. Exige consultas de 3 caracteres o más.
FTS_SONIDO = """
CREATE VIRTUAL TABLE IF NOT EXISTS sonido USING fts5(
    fonetica,
    content='segmento',
    content_rowid='id',
    tokenize='trigram'
);
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "datos", "lacancito.db"))
    ap.add_argument("--rehacer", action="store_true",
                    help="recalcular todo, incluso lo ya calculado")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    preparar(con)

    if args.rehacer:
        con.execute("UPDATE segmento SET fonetica = NULL")
        con.execute("DROP TABLE IF EXISTS sonido")
        con.commit()

    pendientes = con.execute(
        "SELECT count(*) FROM segmento WHERE fonetica IS NULL").fetchone()[0]
    print(f"Fragmentos por procesar: {pendientes:,}")

    hechos = 0
    while True:
        lote = con.execute(
            "SELECT id, texto FROM segmento WHERE fonetica IS NULL LIMIT 5000"
        ).fetchall()
        if not lote:
            break
        con.executemany("UPDATE segmento SET fonetica = ? WHERE id = ?",
                        [(fonetizar(t), i) for i, t in lote])
        con.commit()
        hechos += len(lote)
        print(f"  {hechos:,} / {pendientes:,}", end="\r", flush=True)

    con.executescript(FTS_SONIDO)
    print("\nArmando el índice de sonido…")
    con.execute("INSERT INTO sonido(sonido) VALUES('rebuild')")
    con.commit()

    total, fonemas = con.execute(
        "SELECT count(*), sum(length(fonetica)) FROM segmento").fetchone()
    print(f"Listo: {total:,} fragmentos, {fonemas:,} fonemas indexados.")
    con.close()


if __name__ == "__main__":
    main()
