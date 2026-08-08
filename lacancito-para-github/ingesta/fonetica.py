# -*- coding: utf-8 -*-
"""
Convierte texto francés en cómo suena.

Para qué: Lacan hace equívocos por homofonía. «les non-dupes errent» y
«le Nom-du-Père» suenan igual y no comparten una sola letra en el orden en que
un buscador de texto podría verla. Buscar por letras nunca va a encontrar eso.
Buscar por sonido, sí.

Cómo: el francés es irregular para escribir pero bastante regular para leer, así
que un conjunto de reglas de lectura alcanza. Cada palabra se convierte por
separado —hace falta saber dónde termina para saber qué consonantes son mudas—
y después se pegan todas SIN separación. Esa falta de separación es
deliberada: es lo que hace que «nom du père» y «non-dupes errent» den lo mismo.

Alfabeto (sólo minúsculas y dígitos, para que a la base le dé igual la caja):

    a e i o        como en español
    u   = /u/  de « ou »          y   = /y/  de « tu »
    9   = /ø œ/ de « peu, peur »
    1   = /ɑ̃/  de « an, en »      2   = /ɛ̃ œ̃/ de « vin, un »
    3   = /ɔ̃/  de « on »
    5   = /ʃ/  de « chat »        6   = /ʒ/  de « je »
    7   = /ɲ/  de « agneau »      8   = /ɥ/  de « lui »
    j w        semivocales de « yeux », « oui »
    p b t d k g f v s z m n l r   como se esperaría

No es una transcripción fonética rigurosa y no pretende serlo: es una clave de
búsqueda. Errará en préstamos, nombres propios y en el puñado de finales
ambiguos del francés. Para buscar, equivocarse de más es barato —se descartan
los resultados sobrantes de un vistazo— y equivocarse de menos es caro, porque
lo que no aparece no se sabe que faltó.

Lo que este archivo NO resuelve: las variantes de escritura de una misma
palabra, como « père-version » frente a « Pèreversion ». Al pegarse sin espacio,
la e muda final de « père » deja de ser final y pasa a sonar. Eso es un problema
de grafía, no de homofonía, y le toca a la búsqueda por parecido de escritura.

Corriendo este archivo directamente se ejecutan sus pruebas:

    python fonetica.py
"""
import re
import sys

VOC = "aeiouyéèêëàâîïôöùûü"
V = f"[{VOC}]"

# Palabras donde el final -ent NO es de verbo y por lo tanto suena /ɑ̃/
NO_VERBO_ENT = {
    "argent", "agent", "cent", "dent", "vent", "lent", "gent", "absent",
    "present", "présent", "content", "accent", "evident", "évident",
    "different", "différent", "urgent", "parent", "souvent", "sergent",
    "client", "patient", "orient", "occident", "accident", "incident",
    "continent", "president", "président", "adolescent", "récent", "recent",
    "décent", "arpent", "serpent", "torrent", "couvent", "comment",
    "argument", "instrument", "monument",
}
# Verbos en -ment (3ª del plural), donde -ment NO es el sufijo de adverbio
VERBO_MENT = {
    "aiment", "forment", "dorment", "ferment", "nomment", "arment",
    "charment", "calment", "affirment", "animent", "estiment", "confirment",
    "informent", "transforment", "enferment", "sement",
}
# Palabras donde la s final SÍ suena. « sens » importa: es la mitad de joui-sens
NO_MUDA_S = {
    "sens", "fils", "os", "bus", "autobus", "mars", "ours", "tennis",
    "cactus", "lys", "jadis", "gratis", "bis", "mœurs", "moeurs", "plus",
}
# Palabras cortas donde el final -er suena /ɛʁ/ y no /e/
NO_INFINITIVO_ER = {"hier", "hiver", "cancer", "enfer", "super", "amer", "cuiller"}

TIENE_VOCAL = re.compile(r"[aeiouy1235689]")


def _r(patron):
    return re.compile(patron)


# (regex, salida, sólo_al_final_de_palabra, exige_vocal_ya_emitida)
# El orden manda: se prueba de arriba hacia abajo y gana la primera que entra.
# «exige_vocal» evita que una regla de final se coma el núcleo de la palabra:
# en « dupes » la -es es muda, pero en « les » es la vocal única.
REGLAS = [
    # --- finales de palabra -------------------------------------------------
    (_r(r"amment"), "am1", True, False),
    (_r(r"emment"), "am1", True, False),
    (_r(r"ment"), "m1", True, False),          # adverbios: seulement, vraiment
    (_r(r"aient"), "e", True, True),           # imperfecto: parlaient
    (_r(r"ent"), "", True, True),              # 3ª del plural: errent, disent
    (_r(r"ez"), "e", True, True),
    (_r(r"er"), "e", True, True),              # infinitivo: parler
    (_r(r"ais|ait|ai[ts]?"), "e", True, True),
    (_r(r"es"), "", True, True),               # dupes -> dyp   (pero les -> le)
    (_r(r"e"), "", True, True),                # e muda final:  père -> per
    (_r(r"ps|ts|ds|gs|pt"), "", True, True),   # corps -> kor,  temps -> t1
    (_r(r"[stdxzpg]"), "", True, True),        # consonante final muda
    # --- nasales (vocal + n/m que no arrastra otra vocal ni otra nasal) ------
    (_r(rf"oin(?!{V}|[mn])"), "w2", False, False),
    (_r(rf"ien(?!{V}|[mn])"), "j2", False, False),
    (_r(rf"(?:ain|aim|ein|eim|în|ym|yn|im|in)(?!{V}|[mn])"), "2", False, False),
    (_r(rf"(?:un|um)(?!{V}|[mn])"), "2", False, False),
    (_r(rf"(?:an|am|en|em)(?!{V}|[mn])"), "1", False, False),
    (_r(rf"(?:on|om)(?!{V}|[mn])"), "3", False, False),
    # --- grupos con valor propio -------------------------------------------
    (_r(r"tion"), "sj3", False, False),
    (_r(r"eau|aux|au"), "o", False, False),
    (_r(r"œu|oeu|eu"), "9", False, False),
    (_r(r"ou|oû|où"), "u", False, False),
    (_r(r"oi|oî|oy"), "wa", False, False),
    (_r(r"ai|aî|ei|ay"), "e", False, False),
    (_r(rf"(?<={V})ill"), "j", False, False),
    (_r(r"ill"), "ij", False, False),
    (_r(rf"(?<={V})il"), "j", True, False),
    (_r(r"ch"), "5", False, False),
    (_r(r"ph"), "f", False, False),
    (_r(r"gn"), "7", False, False),
    (_r(r"qu|q"), "k", False, False),
    (_r(r"th"), "t", False, False),
    (_r(r"ss"), "s", False, False),
    (_r(r"([bcdfglmnprtz])\1"), lambda m: m.group(1), False, False),
    # --- letras sueltas dependientes del contexto ---------------------------
    (_r(r"c(?=[eiyéèê])"), "s", False, False),
    (_r(r"c"), "k", False, False),
    (_r(r"ç"), "s", False, False),
    (_r(r"g(?=[eiyéèê])"), "6", False, False),
    (_r(rf"(?<={V})s(?={V})"), "z", False, False),
    (_r(r"x"), "ks", False, False),
    (_r(r"h"), "", False, False),
    (_r(r"j"), "6", False, False),
    (_r(r"w"), "v", False, False),
    # --- vocales sueltas ----------------------------------------------------
    (_r(r"é|è|ê|ë"), "e", False, False),
    (_r(r"à|â"), "a", False, False),
    (_r(r"ô"), "o", False, False),
    (_r(r"ù"), "u", False, False),
    (_r(r"û|u"), "y", False, False),
    (_r(r"î|ï"), "i", False, False),
    (_r(r"y"), "i", False, False),
    (_r(r"[aeiobdfgklmnprstvz]"), lambda m: m.group(0), False, False),
]

PALABRA = re.compile(rf"[{VOC}a-zçœ]+", re.I)


def _leer(w, finales=True):
    """Aplica las reglas. Con finales=False se saltean las reglas de fin de
    palabra: así se tratan los casos de las listas de arriba, recortándoles la
    terminación y leyendo el resto como si el texto siguiera."""
    salida, i, n = [], 0, len(w)
    while i < n:
        for rx, sal, solo_fin, exige_vocal in REGLAS:
            if solo_fin and not finales:
                continue
            m = rx.match(w, i)
            if not m:
                continue
            if solo_fin and m.end() != n:
                continue
            if exige_vocal and not TIENE_VOCAL.search("".join(salida)):
                continue
            salida.append(sal(m) if callable(sal) else sal)
            i = m.end()
            break
        else:
            i += 1                   # carácter que no sabemos leer: se ignora
    return "".join(salida)


def _palabra(w):
    """Los finales ambiguos del francés no se resuelven por regla —«errent» es
    verbo y «argent» no, y terminan igual—, así que van por lista."""
    w = w.lower()
    if w in NO_VERBO_ENT:            # argent, cent: la -ent suena /ɑ̃/
        return _leer(w[:-1], finales=False)
    if w in VERBO_MENT:              # aiment: la -ment no es sufijo de adverbio
        return _leer(w[:-4], finales=False) + "m"
    if w in NO_MUDA_S:               # sens, fils: la s final suena
        return _leer(w[:-1], finales=False) + "s"
    if w in NO_INFINITIVO_ER:        # hier, hiver: la -er no es de infinitivo
        return _leer(w[:-2] + "èr")
    return _leer(w)


def fonetizar(texto):
    """Devuelve cómo suena el texto, sin separación entre palabras."""
    return "".join(_palabra(p) for p in PALABRA.findall(texto))


def localizar(texto, sonido):
    """Dónde, dentro del texto original, se oye `sonido`.

    Hace falta porque la búsqueda ocurre sobre una cadena de fonemas que no
    tiene nada que ver con las letras: para poder mostrar el pasaje hay que
    volver del fonema a la palabra que lo produjo. Devuelve (inicio, fin) en
    caracteres del texto original, o None."""
    if not sonido:
        return None
    palabras, fonemas, de_quien = [], [], []
    for m in PALABRA.finditer(texto):
        f = _palabra(m.group(0))
        i = len(palabras)
        palabras.append((m.start(), m.end()))
        fonemas.append(f)
        de_quien.extend([i] * len(f))
    completo = "".join(fonemas)
    pos = completo.find(sonido)
    if pos < 0:
        return None
    return palabras[de_quien[pos]][0], palabras[de_quien[pos + len(sonido) - 1]][1]


# --------------------------------------------------------------------------
# Pruebas. La primera es la de aceptación de todo el índice fonético.
IGUALES = [
    ("nom du père", "non-dupes errent"),
    ("les non-dupes errent", "les noms du père"),
    ("l'étourdit", "l'étourdi"),
    ("lalangue", "la langue"),
    ("encore", "en corps"),
    ("l'achose", "la chose"),
    ("deux", "d'eux"),
    ("jouissance", "j'ouis sens"),
    ("le temps", "le tan"),
]
DISTINTOS = [
    ("jouissance", "jouissive"),
    ("le père", "la mère"),
    ("signifiant", "signifié"),
    ("symbolique", "symptôme"),
    ("l'imaginaire", "l'imaginer"),
]
SUENAN = [
    ("nom du père", "n3dyper"),
    ("père", "per"),
    ("les", "le"),
    ("cent", "s1"),
    ("errent", "er"),
    ("parler", "parle"),
    ("corps", "kor"),
    ("beaucoup", "boku"),
    ("chose", "5oz"),
    ("jouissance", "6uis1s"),
]


def _pruebas():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fallos = 0
    print("Deben sonar IGUAL:")
    for a, b in IGUALES:
        fa, fb = fonetizar(a), fonetizar(b)
        ok = fa == fb
        fallos += not ok
        print(f"  {'ok ' if ok else 'MAL'}  {a!r} = {fa!r}   |   {b!r} = {fb!r}")
    print("\nDeben sonar DISTINTO:")
    for a, b in DISTINTOS:
        fa, fb = fonetizar(a), fonetizar(b)
        ok = fa != fb
        fallos += not ok
        print(f"  {'ok ' if ok else 'MAL'}  {a!r} = {fa!r}   |   {b!r} = {fb!r}")
    print("\nTranscripciones puntuales:")
    for texto, esperado in SUENAN:
        obtenido = fonetizar(texto)
        ok = obtenido == esperado
        fallos += not ok
        print(f"  {'ok ' if ok else 'MAL'}  {texto!r} -> {obtenido!r}"
              + ("" if ok else f"   (esperado {esperado!r})"))
    print(f"\n{fallos} fallo(s)")
    return fallos


if __name__ == "__main__":
    sys.exit(1 if _pruebas() else 0)
