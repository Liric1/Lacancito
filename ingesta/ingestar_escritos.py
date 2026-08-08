# -*- coding: utf-8 -*-
"""
Ingestor de los *Écrits* (Seuil 1966) y *Autres écrits* (Seuil 2001).

Estos dos son escaneos con OCR, no documentos de texto. Eso cambia todo
respecto de los seminarios:

  * La página que trae el PDF es la página REAL de Seuil. Es la referencia que
    sirve para citar, y por eso vale la pena el trabajo extra.
  * El OCR lee mal algunos números de página ('z6' por '26', 'S4' por '54').
  * El escaneo se salteó las páginas en blanco, así que la diferencia entre la
    página del archivo y la página impresa no es constante: crece a lo largo
    del libro. El texto en cambio corre continuo: no falta contenido.

Por eso la página impresa no se calcula con una resta fija. Se toman como
ANCLAS las páginas donde el número se leyó bien, se descartan las lecturas
imposibles (el desfase solo puede crecer, nunca achicarse) y se rellena entre
anclas. Cada fragmento queda marcado con cuánto vale su número de página:

    exacta      el número estaba impreso en esa misma página y se leyó bien
    verificada  cae entre dos anclas que coinciden en el desfase
    estimada    cae en un tramo donde el desfase cambia; puede errar por 1 o 2

Uso:
    python ingestar_escritos.py "Lacan Jacques Ecrits 1966.pdf" \
        --obra "Écrits" --version "Seuil, 1966" --preview
"""
import argparse
import collections
import difflib
import os
import re
import sys
import unicodedata

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from esquema import guardar  # noqa: E402

ZONA_CABECERA = 28        # el encabezado con el titulo del escrito
ZONA_FOLIO = 60           # franja de abajo donde aparece el numero de pagina
TAM_CUERPO_MIN = 9.3      # por debajo de esto es nota al pie
OBJETIVO_FRAGMENTO = 600

# el OCR confunde estos caracteres con digitos en los numeros de pagina
CONFUSIONES = str.maketrans({"z": "2", "Z": "2", "l": "1", "I": "1", "|": "1",
                             "O": "0", "S": "5", "B": "8"})


def sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def normalizar_titulo(s):
    """Deja el encabezado en una forma comparable pese a los errores del OCR."""
    s = sin_acentos(s).upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z ]", " ", s)).strip()


def limpiar(t):
    t = t.replace("\xad", "")
    t = re.sub(r"(\w)-\s+(?=[a-zà-öø-ÿ])", r"\1", t)   # palabra cortada al fin de linea
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


def es_encabezado(txt):
    """El titulillo corre en versalitas: casi todo mayusculas y corto. Va por ahi
    y no por la posicion, porque los dos libros tienen geometrias distintas."""
    letras = [c for c in txt if c.isalpha()]
    if len(letras) < 4 or len(txt) > 90:
        return False
    return sum(c.isupper() for c in letras) / len(letras) >= 0.75


def leer_paginas(doc):
    """Una pasada por el PDF: encabezado, folio impreso y las dos capas de texto.

    El cuerpo y las notas se separan por tamaño de letra, pero el umbral se
    calcula PARA CADA PÁGINA: en un escaneo el mismo cuerpo mide 8,4 pt en una
    página y 8,1 pt en la siguiente, así que un umbral fijo clasifica mal."""
    paginas = []
    for n in range(doc.page_count):
        pg = doc[n]
        alto = pg.rect.height
        crudas, cabecera, folio = [], None, None

        for b in pg.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b["lines"]:
                txt = "".join(s["text"] for s in l["spans"]).strip()
                if txt:
                    crudas.append((l["bbox"][1], max(s["size"] for s in l["spans"]), txt))
        crudas.sort()

        if crudas and es_encabezado(crudas[0][2]):
            cabecera = crudas.pop(0)[2]

        restantes = []
        for y0, tam, txt in crudas:
            if y0 > alto - ZONA_FOLIO:
                limpio = txt.replace(" ", "").translate(CONFUSIONES)
                if re.fullmatch(r"\d{1,4}", limpio):
                    if folio is None:
                        folio = int(limpio)
                    continue
            restantes.append((y0, tam, txt))

        # tamaño del cuerpo en esta página: el más usado, contando caracteres
        peso = {}
        for _, tam, txt in restantes:
            peso[round(tam, 1)] = peso.get(round(tam, 1), 0) + len(txt)
        tam_cuerpo = max(peso, key=peso.get) if peso else 0

        cuerpo, notas = [], []
        for y0, tam, txt in restantes:
            es_nota = tam < tam_cuerpo - 0.15 and y0 > alto * 0.45
            (notas if es_nota else cuerpo).append(txt)

        paginas.append({"idx": n, "cabecera": cabecera, "folio": folio,
                        "cuerpo": cuerpo, "notas": notas})
    return paginas


def anclas_validas(paginas):
    """Se queda con el subconjunto mas grande de folios leidos que es coherente:
    a medida que avanza el libro, el desfase entre pagina de archivo y pagina
    impresa solo puede crecer (el escaneo omitio blancos, no agrego paginas).
    Es una subsecuencia creciente maxima; descarta las lecturas erroneas."""
    puntos = [(p["idx"], p["folio"]) for p in paginas if p["folio"]]
    if not puntos:
        return []
    # subsecuencia mas larga con folio creciente y desfase no decreciente
    mejor = [1] * len(puntos)
    previo = [-1] * len(puntos)
    for i in range(len(puntos)):
        for j in range(i):
            di, dj = puntos[i][1] - puntos[i][0], puntos[j][1] - puntos[j][0]
            if puntos[j][1] < puntos[i][1] and dj <= di and mejor[j] + 1 > mejor[i]:
                mejor[i], previo[i] = mejor[j] + 1, j
    i = max(range(len(puntos)), key=lambda k: mejor[k])
    cadena = []
    while i >= 0:
        cadena.append(puntos[i])
        i = previo[i]
    return list(reversed(cadena))


def mapear_paginas(paginas):
    """Devuelve {idx: (pagina_impresa, confianza)} para todo el libro."""
    anclas = anclas_validas(paginas)
    if not anclas:
        return {p["idx"]: (p["idx"] + 1, "estimada") for p in paginas}, []

    mapa = {}
    for (i0, f0), (i1, f1) in zip(anclas, anclas[1:]):
        d0, d1 = f0 - i0, f1 - i1
        confianza = "verificada" if d0 == d1 else "estimada"
        for i in range(i0, i1):
            mapa[i] = (i + d0, confianza)
    # los extremos, extrapolando el desfase del ancla mas cercana
    i0, f0 = anclas[0]
    for i in range(0, i0):
        mapa[i] = (i + f0 - i0, "estimada")
    i1, f1 = anclas[-1]
    for i in range(i1, len(paginas)):
        mapa[i] = (i + f1 - i1, "verificada" if i == i1 else "estimada")
    for i, f in anclas:
        mapa[i] = (f, "exacta")
    return mapa, anclas


def agrupar_escritos(paginas):
    """Agrupa paginas consecutivas por el titulo del encabezado. El OCR escribe
    el mismo titulo de formas distintas ('LE SFMINAIRE', 'LB SÉMINAIRE'), asi
    que la comparacion es por parecido, no por igualdad."""
    cabs = [normalizar_titulo(p["cabecera"]) if p["cabecera"] else None
            for p in paginas]

    def representante(g):
        """La variante más repetida del titulillo: el OCR falla distinto cada
        vez, así que la lectura mayoritaria es la buena.

        El desempate alfabético no es cosmético. Sin él, dos lecturas con la
        misma frecuencia se ordenan según el hash de Python, que cambia en cada
        ejecución: el mismo PDF daría un título distinto cada vez que se corre
        la ingesta, y las correcciones a mano dejarían de encontrar su clave."""
        cuenta = collections.Counter(g["variantes"])
        return min(sorted(cuenta), key=lambda v: (-cuenta[v], v))

    def parecido(a, b):
        """Mismo escrito pese al OCR. Además del parecido general se exige que
        coincida el arranque del título: 'Introduction au commentaire de Jean
        Hyppolite' y 'Réponse au commentaire de Jean Hyppolite' se parecen
        mucho y son dos escritos distintos."""
        if not a or not b:
            return False
        if difflib.SequenceMatcher(None, a, b).ratio() < 0.75:
            return False
        return difflib.SequenceMatcher(None, a[:12], b[:12]).ratio() >= 0.6

    for i in range(1, len(cabs) - 1):
        if cabs[i] and not parecido(cabs[i], cabs[i - 1]) \
                and parecido(cabs[i - 1], cabs[i + 1]):
            cabs[i] = cabs[i - 1]

    grupos = []           # cada uno: {"variantes": [...], "idxs": [...]}
    for p, cab in zip(paginas, cabs):
        if not cab or len(cab) < 4:
            p["_grupo"] = None
            continue
        if grupos and parecido(representante(grupos[-1]), cab):
            grupos[-1]["variantes"].append(cab)
            grupos[-1]["idxs"].append(p["idx"])
            continue
        grupos.append({"variantes": [cab], "idxs": [p["idx"]]})

    def absorber(destino, origen):
        grupos[destino]["variantes"] += grupos[origen]["variantes"]
        grupos[destino]["idxs"] = sorted(grupos[destino]["idxs"] + grupos[origen]["idxs"])
        del grupos[origen]

    def pegados():
        """Dos tramos consecutivos que dicen lo mismo son un solo escrito."""
        for i in range(1, len(grupos)):
            if parecido(representante(grupos[i - 1]), representante(grupos[i])):
                absorber(i - 1, i)
                return True
        return False

    def emparedados():
        """Un escrito ocupa páginas contiguas: si el tramo anterior y el
        posterior son el mismo escrito, lo del medio también lo es, por mal que
        se haya leído su titulillo. No importa cuánto ocupe."""
        for i in range(1, len(grupos) - 1):
            if parecido(representante(grupos[i - 1]), representante(grupos[i + 1])):
                absorber(i - 1, i + 1)
                absorber(i - 1, i)
                return True
        return False

    def sueltos():
        """Un tramo de una o dos páginas al borde de un escrito rara vez es un
        escrito nuevo: suele ser el mismo con el titulillo destrozado. Se lo
        anexa al vecino al que más se parezca, con una exigencia más floja."""
        def flojo(a, b):
            return difflib.SequenceMatcher(None, a or "", b or "").ratio()
        for i in range(len(grupos)):
            if len(grupos[i]["idxs"]) > 2 or len(grupos) == 1:
                continue
            yo = representante(grupos[i])
            antes = flojo(yo, representante(grupos[i - 1])) if i > 0 else 0
            despues = flojo(yo, representante(grupos[i + 1])) if i + 1 < len(grupos) else 0
            if max(antes, despues) < 0.6:
                continue
            absorber(i - 1 if antes >= despues else i + 1, i)
            return True
        return False

    while pegados() or emparedados() or sueltos():
        pass

    for n_g, g in enumerate(grupos):
        for idx in g["idxs"]:
            paginas[idx]["_grupo"] = n_g

    # las paginas sin encabezado (aperturas de escrito, laminas) van con la
    # siguiente que si lo tenga: una apertura pertenece al escrito que abre
    siguiente = None
    for p in reversed(paginas):
        if p["_grupo"] is None:
            p["_grupo"] = siguiente
        else:
            siguiente = p["_grupo"]

    return [representante(g).title() for g in grupos]


def cargar_correcciones(ruta):
    """Los titulillos vienen del encabezado impreso, leído por OCR, así que
    algunos salen rotos. El archivo de correcciones permite arreglarlos a mano
    sin tocar el código. Formato, una por línea:

        Écrits :: Du Rif B Ne Freud :: Du « Trieb » de Freud

    Un guion solo como corrección significa 'esto no es un escrito' (colofones,
    ISBN, numerales de sección): esas páginas quedan sin escrito asignado.

        Autres écrits :: Isbn :: -

    Se ignoran las líneas vacías y las que empiezan con #."""
    if not ruta or not os.path.exists(ruta):
        return {}
    corr = {}
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            partes = [p.strip() for p in linea.split("::")]
            if len(partes) == 3 and partes[2]:
                corr[(partes[0], partes[1])] = None if partes[2] == "-" else partes[2]
    return corr


def ingestar(ruta_pdf, obra, version, autor="Jacques Lacan", idioma="fr",
             correcciones=None):
    doc = pymupdf.open(ruta_pdf)
    archivo = os.path.basename(ruta_pdf)
    paginas = leer_paginas(doc)
    mapa, anclas = mapear_paginas(paginas)
    titulos = agrupar_escritos(paginas)
    doc.close()

    corr = correcciones or {}
    detectados = list(titulos)
    titulos = [corr.get((obra, t), t) for t in titulos]

    segmentos = []
    for p in paginas:
        pagina, confianza = mapa.get(p["idx"], (p["idx"] + 1, "estimada"))
        escrito = titulos[p["_grupo"]] if p["_grupo"] is not None else None
        for capa, lineas in (("lacan", p["cuerpo"]), ("nota", p["notas"])):
            texto = limpiar(" ".join(lineas))
            for i, frag in enumerate(fragmentar(texto), start=1):
                segmentos.append({
                    "archivo": archivo, "autor": autor, "obra": obra,
                    "escrito": escrito, "version": version, "idioma": idioma,
                    "capa": capa, "pagina": pagina,
                    "pagina_confianza": confianza, "pagina_pdf": p["idx"] + 1,
                    "orden": i, "texto": frag,
                })
    return segmentos, titulos, anclas, paginas, detectados


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--obra", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--db", default=None)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--titulos", action="store_true", help="listar los escritos")
    ap.add_argument("--correcciones", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "datos", "titulos.txt"))
    ap.add_argument("--exportar-titulos", action="store_true",
                    help="agregar los títulos detectados al archivo de correcciones")
    args = ap.parse_args()

    corr = cargar_correcciones(args.correcciones)
    segs, titulos, anclas, paginas, detectados = ingestar(
        args.pdf, args.obra, args.version, correcciones=corr)
    cuerpo = [s for s in segs if s["capa"] == "lacan"]
    conf = {}
    for s in cuerpo:
        conf[s["pagina_confianza"]] = conf.get(s["pagina_confianza"], 0) + 1

    print(f"Obra          : {args.obra}  ({args.version})")
    print(f"Páginas PDF   : {len(paginas)}")
    print(f"Anclas de folio usadas: {len(anclas)} "
          f"(de {sum(1 for p in paginas if p['folio'])} números leídos)")
    if anclas:
        print(f"  desfase inicial {anclas[0][1]-anclas[0][0]:+d} "
              f"→ final {anclas[-1][1]-anclas[-1][0]:+d}")
    print(f"Escritos detectados: {len(titulos)}")
    print(f"Fragmentos    : {len(cuerpo)} de cuerpo, "
          f"{len(segs)-len(cuerpo)} de notas, "
          f"{sum(len(s['texto']) for s in cuerpo):,} caracteres")
    print("Confianza del número de página (fragmentos de cuerpo):")
    for k in ("exacta", "verificada", "estimada"):
        n = conf.get(k, 0)
        print(f"   {k:<11} {n:>6}  {100*n/max(1,len(cuerpo)):5.1f}%")

    # una corrección cuya clave ya no existe se saltearía en silencio, y eso es
    # peor que no tenerla: uno cree que el título está arreglado y no lo está
    huerfanas = [c for (o, c) in corr if o == args.obra and c not in detectados]
    if huerfanas:
        print(f"\n!! {len(huerfanas)} corrección(es) de {args.correcciones} no se"
              f" aplicaron: su clave ya no coincide con ningún título detectado.")
        for c in huerfanas:
            print(f"     {c!r}")

    if args.titulos:
        print("\nEscritos, en orden:")
        for i, (t, det) in enumerate(zip(titulos, detectados), 1):
            if t is None:
                print(f"  {i:>2}. (no es un escrito: {det})")
                continue
            pags = [s["pagina"] for s in cuerpo if s["escrito"] == t]
            rango = f"pp. {min(pags)}–{max(pags)}" if pags else "(sin texto)"
            print(f"  {i:>2}. {t:<62} {rango}")

    if args.exportar_titulos:
        os.makedirs(os.path.dirname(args.correcciones), exist_ok=True)
        nuevo = not os.path.exists(args.correcciones)
        with open(args.correcciones, "a", encoding="utf-8") as fh:
            if nuevo:
                fh.write(
                    "# Títulos de los escritos, tal como los leyó el OCR del\n"
                    "# encabezado de cada página. Corregí el texto que va DESPUÉS\n"
                    "# del segundo :: y volvé a correr la ingesta. No toques lo\n"
                    "# que va antes: es la clave con la que se busca la línea.\n\n")
            fh.write(f"# --- {args.obra} ---\n")
            for det, fin in zip(detectados, titulos):
                fh.write(f"{args.obra} :: {det} :: {fin if fin else '-'}\n")
        print(f"\nTítulos volcados en {args.correcciones}")

    if args.preview:
        print("\n" + "=" * 78)
        for s in cuerpo[:1] + cuerpo[len(cuerpo)//2:len(cuerpo)//2+2]:
            print(f"\n[{s['obra']} · {s['escrito']} · p. {s['pagina']} "
                  f"({s['pagina_confianza']})]")
            print("  " + s["texto"][:420])

    if args.db:
        print(f"\nGuardados {guardar(segs, args.db)} fragmentos en {args.db}")


if __name__ == "__main__":
    main()
