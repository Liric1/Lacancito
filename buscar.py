# -*- coding: utf-8 -*-
"""
Buscador sobre la base de Lacancito.

    python buscar.py "il n'y a pas de rapport sexuel"      buscar una cita
    python buscar.py jouissance --contar                   cuantas veces y donde
    python buscar.py jouissance --contar --por anio        por año
    python buscar.py angoisse --obra "Seminario 10"        acotar a una obra
    python buscar.py --alrededor 12345                     ver el contexto de un
                                                           fragmento por su numero

Por defecto busca solo en la capa 'lacan' (las palabras de Lacan). Con
--capa editor busca en los comentarios del transcriptor, y con --capa nota
en las notas al pie.
"""
import argparse
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingesta"))
from fonetica import fonetizar, localizar  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos", "lacancito.db")

FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS busqueda USING fts5(
    texto,
    content='segmento',
    content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
"""


def conectar(ruta):
    if not os.path.exists(ruta):
        sys.exit(f"No existe la base {ruta}. Corré primero la ingesta.")
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    return con


def asegurar_indice(con):
    """Reconstruye el indice de busqueda si la base cambio.

    Ojo: en una tabla FTS5 con content externo, 'SELECT count(*) FROM busqueda'
    cuenta las filas de segmento, no las del indice — no sirve para saber si el
    indice esta armado. Por eso anotamos aparte cuantas filas indexamos."""
    con.executescript(FTS)
    con.execute("CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT)")
    n_seg = con.execute("SELECT count(*) FROM segmento").fetchone()[0]
    fila = con.execute("SELECT valor FROM meta WHERE clave='indexados'").fetchone()
    if not fila or int(fila[0]) != n_seg:
        print(f"(indexando {n_seg:,} fragmentos, una sola vez...)", file=sys.stderr)
        con.execute("INSERT INTO busqueda(busqueda) VALUES('rebuild')")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('indexados', ?)", (str(n_seg),))
        con.commit()


def cita(f):
    partes = [f["obra"]]
    if f["escrito"]:
        partes.append(f"«{f['escrito']}»")
    if f["sesion_n"]:
        partes.append(f"clase {f['sesion_n']} del {f['sesion_fecha']}")
    elif f["sesion_fecha"]:
        partes.append(f["sesion_fecha"])
    pag = f"p. {f['pagina']}"
    if f["pagina_confianza"] == "estimada":
        pag += " (aprox.)"
    partes.append(pag)
    if f["capa"] != "lacan":
        partes.append(f"[{f['capa']}]")
    return " · ".join(partes)


def buscar(con, consulta, capa, obra, limite, familia=None, parte=None):
    where = ["busqueda MATCH ?"]
    args = [consulta]
    if capa != "todas":
        where.append("s.capa = ?")
        args.append(capa)
    if obra:
        where.append("s.obra LIKE ?")
        args.append(f"%{obra}%")
    if familia:
        where.append("s.familia = ?")
        args.append(familia)
    # parte = una clase de un seminario, un escrito, o una pieza suelta.
    # Las piezas de «Otros» comparten titulo (hay decenas de «Pneumatique a
    # Pierre Soury»), asi que ahi hace falta ademas la fecha para distinguirlas.
    if parte:
        if parte.get("sesion"):
            where.append("s.sesion_n = ?")
            args.append(parte["sesion"])
        if parte.get("escrito"):
            where.append("s.escrito = ?")
            args.append(parte["escrito"])
        if parte.get("fecha"):
            where.append("s.sesion_fecha = ?")
            args.append(parte["fecha"])
    total = con.execute(
        f"""SELECT count(*) FROM busqueda JOIN segmento s ON s.id = busqueda.rowid
            WHERE {' AND '.join(where)}""", args).fetchone()[0]
    filas = con.execute(f"""
        SELECT s.*, snippet(busqueda, 0, '»»', '««', ' … ', 24) AS frag,
               bm25(busqueda) AS puntaje
        FROM busqueda JOIN segmento s ON s.id = busqueda.rowid
        WHERE {' AND '.join(where)}
        ORDER BY puntaje LIMIT ?""", args + [limite]).fetchall()
    return filas, total, linea_de_tiempo(con, "busqueda", where, args)


def buscar_por_sonido(con, consulta, capa, obra, limite, familia=None,
                      parte=None):
    """Busca por cómo suena, no por cómo se escribe. Encuentra los equívocos:
    «nom du père» devuelve también «les non-dupes errent»."""
    sonido = fonetizar(consulta)
    if len(sonido) < 3:
        sys.exit("La búsqueda por sonido necesita al menos tres fonemas.")
    where = ["sonido MATCH ?"]
    args = ['"' + sonido + '"']
    if capa != "todas":
        where.append("s.capa = ?")
        args.append(capa)
    if obra:
        where.append("s.obra LIKE ?")
        args.append(f"%{obra}%")
    if familia:
        where.append("s.familia = ?")
        args.append(familia)
    # parte = una clase de un seminario, un escrito, o una pieza suelta.
    # Las piezas de «Otros» comparten titulo (hay decenas de «Pneumatique a
    # Pierre Soury»), asi que ahi hace falta ademas la fecha para distinguirlas.
    if parte:
        if parte.get("sesion"):
            where.append("s.sesion_n = ?")
            args.append(parte["sesion"])
        if parte.get("escrito"):
            where.append("s.escrito = ?")
            args.append(parte["escrito"])
        if parte.get("fecha"):
            where.append("s.sesion_fecha = ?")
            args.append(parte["fecha"])
    total = con.execute(
        f"""SELECT count(*) FROM sonido JOIN segmento s ON s.id = sonido.rowid
            WHERE {' AND '.join(where)}""", args).fetchone()[0]
    filas = con.execute(f"""
        SELECT s.* FROM sonido JOIN segmento s ON s.id = sonido.rowid
        WHERE {' AND '.join(where)}
        ORDER BY s.obra, s.pagina LIMIT ?""", args + [limite]).fetchall()
    return sonido, filas, total, linea_de_tiempo(con, "sonido", where, args)


def linea_de_tiempo(con, tabla, where, args):
    """Cuántos resultados caen en cada año. Se calcula sobre TODOS los que
    dieron, no sobre los que se muestran: es el mapa de la búsqueda."""
    sql = f"""
        SELECT substr(s.sesion_fecha,1,4) AS anio, count(*) n
        FROM {tabla} JOIN segmento s ON s.id = {tabla}.rowid
        WHERE {' AND '.join(where)} AND s.sesion_fecha IS NOT NULL
        GROUP BY anio ORDER BY anio"""
    return [{"anio": r[0], "n": r[1]} for r in con.execute(sql, args)]


def frase_cercania(consulta, distancia=10):
    """Traduce «goce mujer» a la sintaxis de proximidad del motor: las dos
    palabras a menos de N de distancia, en cualquier orden."""
    palabras = [w for w in re.findall(r"[\w'’-]+", consulta) if len(w) > 1]
    if len(palabras) < 2:
        return None
    return f"NEAR({' '.join(palabras)}, {int(distancia)})"


def recorte(texto, ini, fin, margen=90):
    """Un pasaje del texto con el hallazgo marcado."""
    a, b = max(0, ini - margen), min(len(texto), fin + margen)
    return (("… " if a else "") + texto[a:ini] + "»»" + texto[ini:fin] + "««"
            + texto[fin:b] + (" …" if b < len(texto) else ""))


def contar(con, consulta, capa, por):
    campo = {"obra": "s.obra", "anio": "substr(s.sesion_fecha,1,4)",
             "clase": "s.obra || ' · clase ' || s.sesion_n"}[por]
    cond = "" if capa == "todas" else "AND s.capa = :capa"
    sql = f"""
        SELECT {campo} AS grupo, count(*) AS n,
               min(s.sesion_fecha) AS desde, max(s.sesion_fecha) AS hasta
        FROM busqueda JOIN segmento s ON s.id = busqueda.rowid
        WHERE busqueda MATCH :q {cond}
        GROUP BY grupo ORDER BY {'grupo' if por == 'anio' else 'n DESC'}"""
    return con.execute(sql, {"q": consulta, "capa": capa}).fetchall()


def alrededor(con, id_frag, radio):
    f = con.execute("SELECT * FROM segmento WHERE id = ?", (id_frag,)).fetchone()
    if not f:
        sys.exit(f"No existe el fragmento {id_frag}")
    vecinos = con.execute(
        """SELECT * FROM segmento
           WHERE obra = ? AND capa = ? AND id BETWEEN ? AND ?
           ORDER BY id""",
        (f["obra"], f["capa"], id_frag - radio, id_frag + radio)).fetchall()
    print(f"\n{cita(f)}\n" + "-" * 78)
    for v in vecinos:
        marca = ">>> " if v["id"] == id_frag else "    "
        print(f"{marca}[{v['id']} · p.{v['pagina']}] {v['texto']}\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("consulta", nargs="?", default=None)
    ap.add_argument("--capa", default="lacan",
                    choices=["lacan", "editor", "nota", "todas"])
    ap.add_argument("--obra", default=None)
    ap.add_argument("--limite", type=int, default=10)
    ap.add_argument("--sonido", action="store_true",
                    help="buscar por cómo suena en francés, no por cómo se escribe")
    ap.add_argument("--contar", action="store_true")
    ap.add_argument("--por", default="obra", choices=["obra", "anio", "clase"])
    ap.add_argument("--alrededor", type=int, default=None)
    ap.add_argument("--radio", type=int, default=1)
    ap.add_argument("--db", default=DB)
    args = ap.parse_args()

    con = conectar(args.db)
    asegurar_indice(con)

    if args.alrededor is not None:
        alrededor(con, args.alrededor, args.radio)
        return
    if not args.consulta:
        sys.exit("Falta qué buscar.")

    if args.sonido:
        son, filas, total, _ = buscar_por_sonido(con, args.consulta, args.capa,
                                                 args.obra, args.limite)
        de_mas = f" (se muestran {len(filas)})" if total > len(filas) else ""
        print(f'\n«{args.consulta}» suena /{son}/ — {total} resultados{de_mas}\n')
        for f in filas:
            ubic = localizar(f["texto"], son)
            pasaje = recorte(f["texto"], *ubic) if ubic else f["texto"][:260]
            print(f"  {cita(f)}   (fragmento {f['id']})")
            print(f"     {pasaje}\n")
        return

    # si el usuario escribio varias palabras sin comillas, lo tomamos como frase
    q = args.consulta
    if " " in q and not re.search(r'["*]|\bOR\b|\bNOT\b', q):
        q = '"' + q.replace('"', '') + '"'

    if args.contar:
        filas = contar(con, q, args.capa, args.por)
        total = sum(f["n"] for f in filas)
        print(f'\n«{args.consulta}» — {total} fragmentos, en {len(filas)} '
              f'{ {"obra": "obras", "anio": "años", "clase": "clases"}[args.por] }\n')
        for f in filas:
            barra = "█" * min(40, max(1, round(f["n"] * 40 / max(x["n"] for x in filas))))
            print(f"  {f['grupo'] or '?':<52} {f['n']:>5}  {barra}")
        return

    filas, total, _ = buscar(con, q, args.capa, args.obra, args.limite)
    if not filas:
        print(f"Sin resultados para «{args.consulta}».")
        return
    de_mas = f" (se muestran {len(filas)})" if total > len(filas) else ""
    print(f'\n«{args.consulta}» — {total} resultados{de_mas}\n')
    for f in filas:
        print(f"  {cita(f)}   (fragmento {f['id']})")
        print(f"     {f['frag']}\n")


if __name__ == "__main__":
    main()
