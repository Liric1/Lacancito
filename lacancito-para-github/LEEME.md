# Lacancito

Buscador de citas de Lacan con referencia verificable: seminario, número de
clase, fecha de la clase y página.

Estado: **28 seminarios + *Écrits* + *Autres écrits*, todo en francés.**
Faltan las conferencias, Freud, Miller y las traducciones al castellano.

---

## Qué hay adentro

```
lacancito/
  Lacancito.bat             ►► DOBLE CLIC ACÁ para usarlo ◄◄
  app.py                    la página web
  buscar.py                 el buscador (también sirve desde la terminal)
  ingesta/
    esquema.py              la forma de la base; la comparten los ingestores
    fonetica.py             cómo suena cada palabra en francés
    ingestar_seminario.py   convierte UN PDF de seminario en filas de la base
    ingestar_todos.py       corre lo anterior sobre una carpeta entera
    ingestar_escritos.py    los Écrits y Autres écrits (son escaneos con OCR)
    indexar_fonetica.py     arma el índice de búsqueda por sonido
  datos/
    lacancito.db            la base. Un solo archivo. Se puede copiar y mover.
    titulos.txt             correcciones a mano de los títulos de los escritos
```

## Cómo se usa

**Doble clic en `Lacancito.bat`.** Se abre una ventana negra —hay que dejarla
abierta, es el motor— y enseguida el navegador con la página. Se escribe en el
casillero y listo. Para cerrar todo, se cierra la ventana negra.

Nada de esto sale a internet: la página, la base y el buscador están todos en
esta computadora.

Los filtros van en cascada, de lo general a lo particular: **obra → familia →
parte**. Elegís un seminario y aparecen sus clases con la fecha; elegís
*Écrits* y aparecen los escritos con su rango de páginas; elegís *Otros* y
aparecen las piezas, cada una con su fecha —que es lo que distingue las
decenas de *Pneumatique à Pierre Soury* entre sí—.

La página tiene cuatro modos:

- **Texto exacto** — varias palabras se buscan como frase entera. No hace falta
  poner los acentos.
- **Por cómo suena** — encuentra los equívocos. Ver más abajo.
- **Palabras cerca** — dos o más palabras a menos de N palabras de distancia, en
  cualquier orden. Encuentra donde dos nociones se cruzan sin depender de cómo
  estén formuladas: `jouissance femme` como frase exacta no aparece nunca; a
  diez palabras de distancia aparece 69 veces, y a cincuenta, 121.
- **Contar** — el panel de análisis. No muestra texto: muestra las cuentas.

Debajo del casillero, una **línea de tiempo** muestra en qué años cae lo que
buscaste, de 1926 a 1981. Se dibujan también los años en cero, porque el hueco
dice tanto como el pico: cuándo Lacan dejó de usar una palabra.

Y en cada resultado: *ver alrededor* muestra los fragmentos vecinos, *ver la
cita completa* la deja en APA lista para pegar, *traducir en DeepL* abre el
pasaje en el traductor, *ver la página original* dibuja la página del PDF tal
cual —sirve para verificar contra el papel una transcripción marcada en rojo—,
y *avisar de un error* arma un reporte con la referencia y el texto.

La app no traduce nada por su cuenta: te lleva al traductor con el texto ya
puesto. Manda el fragmento completo y limpio, no el recorte con el resaltado.
El más largo del corpus tiene 2.012 caracteres, bastante debajo del límite de
DeepL. **Es lo único de todo esto que sale a internet:** ese fragmento viaja a
DeepL cuando apretás el enlace.

## Desde la terminal (opcional)

Todo lo que hace la página se puede hacer también escribiendo comandos. Sirve
para revisar el corpus, no para el uso diario.

```bash
python buscar.py "il n'y a pas de rapport sexuel"
python buscar.py "nom du père" --sonido
```

Contar una palabra y ver dónde aparece:

```bash
python buscar.py jouissance --contar --por anio
```

`--por` acepta `obra`, `anio` o `clase`.

Ver qué venía antes y después de un resultado (el número sale en cada
resultado, entre paréntesis):

```bash
python buscar.py --alrededor 53347 --radio 2
```

Acotar a una obra:

```bash
python buscar.py angoisse --obra "Seminario 10"
```

Volver a construir la base desde cero:

```bash
python ingesta/ingestar_todos.py "C:\Users\Waldo\Desktop\Formalizando\0Lacan\0LACAN" --db datos/lacancito.db
```

## Qué contiene la base

Una sola tabla, `segmento`. Cada fila es un fragmento de texto de unos 600
caracteres cortado en fin de frase, con estos datos pegados:

| campo | qué es |
|---|---|
| `obra` | Seminario 20 — Aún |
| `sesion_n`, `sesion_fecha` | número de clase y fecha, en formato `1973-02-20` |
| `pagina`, `pagina_pdf` | página impresa en el PDF, y página física del archivo |
| `capa` | `lacan`, `editor` o `nota` (ver abajo) |
| `version` | de qué establecimiento del texto viene |
| `texto` | el fragmento |

### Las tres capas

Los PDF usados son las versiones de trabajo de Staferla, que distinguen
tipográficamente lo que dijo Lacan de lo que agregó el transcriptor. El
ingestor respeta esa distinción y la guarda:

- **`lacan`** — cuerpo del texto, Garamond 10 pt. Las palabras de Lacan.
- **`editor`** — comentarios del transcriptor, acotaciones tipo `[Rires]`,
  remisiones bibliográficas. El propio documento lo declara: *"Ce qui
  s'inscrit entre crochets droits [ ] n'est pas de Jacques Lacan"*.
- **`nota`** — notas al pie.

Las búsquedas usan solo la capa `lacan` salvo que se pida otra cosa con
`--capa`. Esto importa: sin la separación, una búsqueda de "angoisse"
devolvería también las veces que la palabra aparece en un comentario ajeno,
atribuido a Lacan.

## Lo que está verificado y lo que no

**Verificado.** Cada PDF trae una tabla de sesiones cuyas entradas son
enlaces internos a la página exacta donde empieza cada clase. El ingestor usa
esos enlaces y después contrasta cuántas clases encontró contra cuántas
declara la tabla. Los 28 seminarios dan la cuenta exacta, salvo dos:

- **Seminario 3** y **Seminario 6** no traen tabla de sesiones enlazada. Sus
  clases se detectaron por el encabezado impreso en cada página, que funciona,
  pero no hay contra qué contrastarlo. Conviene revisarlos a mano.

**No verificado en los seminarios.** El número de página es el del PDF de
Staferla, **no el de Seuil**. Para los seminarios la cita canónica es
*seminario + fecha de la clase*, que sí es correcta y no depende de la edición.

## Los *Écrits* y los *Autres écrits*

Estos dos son otra cosa: escaneos con OCR de las ediciones de Seuil. Cuestan
más trabajo pero valen la pena, porque **su número de página es el de Seuil**,
o sea el que sirve para citar de verdad.

Dos problemas y cómo se resolvieron:

**El OCR lee mal los números de página** (`z6` por `26`, `S4` por `54`), y el
escaneo se salteó las páginas en blanco entre secciones, así que la diferencia
entre página del archivo y página impresa no es constante: en los *Écrits* va
de +6 al principio a +26 al final. (El texto en cambio corre continuo: no
falta contenido, sólo blancos.) La solución no es una resta fija sino tomar
como anclas las páginas donde el número se leyó bien, descartar las lecturas
imposibles —el desfase sólo puede crecer— y rellenar entre anclas. Cada
fragmento queda marcado con cuánto vale su página:

| | *Écrits* | *Autres écrits* |
|---|---|---|
| `exacta` — el número estaba impreso ahí y se leyó bien | 26 % | 94 % |
| `verificada` — cae entre dos anclas que coinciden | 52 % | 5 % |
| `estimada` — puede errar por 1 o 2 | 22 % | 1 % |

Las estimadas aparecen en los resultados como `p. 492 (aprox.)`. No son un
error escondido: son una página que puede estar corrida por uno.

**Cada escrito hay que saber dónde empieza y termina.** Se detecta por el
titulillo que corre en el encabezado de cada página, agrupando páginas
seguidas. Como el OCR escribe el mismo título distinto cada vez
(`LE SFMINAIRE`, `LB SÉMINAIRE`), la comparación es por parecido, y se aplican
tres reglas de sentido común: dos tramos pegados que dicen lo mismo son uno;
si el tramo de antes y el de después son el mismo escrito, lo del medio
también lo es (un escrito ocupa páginas contiguas); y un tramo de una o dos
páginas al borde de otro es casi siempre el mismo con el título ilegible.

Salen 44 escritos en los *Écrits* y 49 en los *Autres écrits*, con rangos que
coinciden con la paginación real de Seuil (*Le stade du miroir* 93–100,
*Kant avec Sade* 765–790, *L'étourdit* 449–495).

### Corregir los títulos a mano

Los títulos vienen del encabezado leído por OCR, así que unos pocos salen
rotos. Se corrigen en `datos/titulos.txt`, que es un archivo de texto común.
Cada línea tiene tres partes separadas por `::`:

```
Écrits :: Du Rif B Ne Freud :: Du « Trieb » de Freud et du désir du psychanalyste
```

Se edita **sólo lo que va después del segundo `::`**. Lo de antes es la clave
con la que el programa encuentra la línea; si se toca, deja de funcionar.
Después hay que volver a correr la ingesta de ese libro.

## La búsqueda por sonido

Buscar por letras no puede encontrar lo que Lacan hace sonar igual. En este
corpus, `les non-dupes errent` aparece 12 veces y `Nom-du-Père` 128, son la
misma cosa, y ningún buscador de texto puede relacionarlas: no comparten nada
que se pueda ver en la escritura.

Por eso cada fragmento guarda, además del texto, **cómo suena**. Las reglas de
lectura del francés están en [`ingesta/fonetica.py`](ingesta/fonetica.py), que
además trae sus propias pruebas:

```bash
python ingesta/fonetica.py
```

Dos decisiones de diseño que conviene conocer:

**Los sonidos se guardan sin separación entre palabras.** `nom du père` y
`non-dupes errent` dan los dos `n3dyper`. Si se guardaran separados por
palabra, no coincidirían nunca: el equívoco está justamente en que el corte
entre palabras es distinto.

**El texto guardado no se normaliza jamás.** Apóstrofes, acentos, guiones y
puntos suspensivos quedan exactamente como están, porque en Lacan la tipografía
es parte del chiste: `L'étourdit` no es `L'étourdi`, `... ou pire` no es
`ou pire`. Lo que se normaliza es el índice, que es una estructura aparte que
nadie ve.

El conversor no es una transcripción fonética rigurosa y no pretende serlo: es
una clave de búsqueda. Va a errar en préstamos, nombres propios y en los
finales ambiguos del francés (`errent` es verbo y `argent` no, y terminan
igual). Para buscar, equivocarse de más es barato —se descartan los sobrantes
de un vistazo— y equivocarse de menos es caro, porque lo que no aparece no se
sabe que faltó.

Lo que **no** resuelve son las variantes de escritura de una misma palabra,
como `père-version` frente a `Pèreversion`. Eso es un problema de grafía, no de
homofonía, y le toca a la búsqueda por parecido, que todavía no está.

Después de cada ingesta hay que rearmar el índice:

```bash
python ingesta/indexar_fonetica.py --db datos/lacancito.db
```

## El panel de análisis (modo «Contar»)

Escribís una palabra —o varias separadas por coma, hasta tres, para
superponerlas— y salen cuatro gráficos y seis números.

**Frecuencia relativa, por cada 10.000 palabras del año.** Es el gráfico que
importa y la razón es concreta: en 1967 Lacan habló mucho más que en 1953, así
que el conteo en bruto favorece siempre a los años cargados. Con `jouissance`
se ve enseguida: su pico **absoluto** cae en 1967, pero el **relativo** en 1973,
el año de *Encore*. Son dos afirmaciones distintas y sólo la segunda dice algo.

**Frecuencia absoluta** y **acumulado**. El acumulado muestra cuándo un
concepto irrumpe y cuándo se estanca: `sinthome` no existe hasta 1975 y se
concentra en cuatro años.

**Reparto por obra**, y seis números por término: primera y última aparición,
pico absoluto, pico relativo, en cuántas obras aparece, y un índice de
concentración de 0 a 1 (0 = repartido parejo entre las obras; 1 = todo en una
sola). `désir` da 0,57 en 31 obras; `sinthome` da 0,64 en 5.

El denominador —cuántas palabras tiene el corpus cada año— se calcula del
propio corpus, así que se mantiene solo al agregar textos.

### Las fechas de los Écrits

Un análisis temporal necesita que todo tenga fecha, y los fragmentos de
*Écrits* y *Autres écrits* no la traen: un libro tiene año de publicación, no
fecha de escritura. Se resolvió emparejando cada escrito con su entrada en el
sumario del assemblage, que sí fecha cada pieza. Entraron **48 de los 90**, los
que emparejan con seguridad; por debajo de cierto parecido el emparejamiento se
equivoca (*Postface au Séminaire XI* caía sobre *Préliminaire à R.S.I.*) y se
descartan. Los fragmentos sin fecha bajaron del 11% al 5%, y el panel siempre
dice cuántos quedaron afuera de cada gráfico.

## El catálogo «Otros»

Lo que no está en los seminarios ni en los dos volúmenes de *Écrits* sale del
**assemblage chronologique**, un documento de trabajo interno de la école
lacanienne de psychanalyse que reúne toda la obra en orden de fecha. De sus
1.017 piezas, 599 ya las teníamos; **343 son material que no está en libro**:
conferencias en el extranjero, entrevistas, cartas, intervenciones, casos
clínicos de los años 30, notas.

Cada pieza lleva su **familia**, que sirve de filtro: cartas y notas privadas,
intervenciones y discusiones, conferencias fuera del seminario, entrevistas,
casos clínicos, congresos, escuela, prefacios.

Se citan por la pieza, no por el volumen:

> Lacan, J. (1966-02-16). La place de la psychanalyse dans la médecine. En
> *Pour une recherche : assemblage chronologique* [documento de trabajo
> interno]. École lacanienne de psychanalyse.

### Lo que sale en rojo

Algunas piezas del volumen **no son transcripciones**: la página del
*Pneumatique à Pierre Soury* es la foto de una nota manuscrita, no su texto.
Otras vienen de un OCR pobre. Esos fragmentos aparecen **en rojo** con un
aviso, porque conviene verificarlos contra el original antes de citarlos.

Se detectan de dos maneras: cuando la pieza devuelve muy poco texto para las
páginas que ocupa —señal de que la página es una imagen—, y cuando el fragmento
tiene demasiadas palabras de una o dos letras, que es la firma de un OCR que
perdió caracteres. Los seminarios limpios rondan el 34% de esas palabras; por
encima del 48% se marca.

Son 158 fragmentos de 72.329. Si encontrás uno mal marcado, en cualquier
sentido, avisá: el umbral se ajusta en `ingesta/ingestar_otros.py`.

Cada resultado tiene además **avisar de un error**, que arma un reporte con el
número de fragmento, la referencia y el texto tal como está. Lo copia al
portapapeles y lo muestra en un cuadro seleccionable, porque el portapapeles
del navegador no siempre funciona y el aviso no debería depender de eso.

## Volumen actual

31 obras · **72.329 fragmentos** · 31,5 millones de caracteres · 18,3 millones
de fonemas indexados para la búsqueda por sonido.

28 seminarios · *Écrits* y *Autres écrits* con 90 escritos identificados ·
343 piezas en «Otros». Casi todo en francés, con 670 fragmentos en castellano
y 402 en inglés.

## Al editar `datos/titulos.txt`

La clave de cada línea es el título tal como lo detecta el programa. Si esa
detección cambia, la corrección deja de encontrar su línea. Por eso la ingesta
avisa cuando una corrección no se aplicó:

```
!! 1 corrección(es) no se aplicaron: su clave ya no coincide
     'Preface A Veveil Du Printemps'
```

Ese aviso hay que atenderlo: sin él uno cree que el título está arreglado y no
lo está. Pasó de verdad durante la construcción, por dos motivos distintos:
mejorar la agrupación cambió algunos títulos detectados, y —peor— la detección
misma era no determinista. Cuando dos lecturas del titulillo empataban en
frecuencia, `max()` sobre un conjunto elegía según el orden de hash de Python,
que cambia en cada ejecución: el mismo PDF daba un título distinto cada vez. El
desempate alfabético en `representante()` lo arregla, y por eso está comentado
en el código: parece cosmético y no lo es.

## Pendiente

1. Conferencias y textos sueltos.
2. Castellano, para poder buscar en una lengua y citar en la otra.
3. Freud y Miller.
4. Búsqueda difusa y por sentido (hoy la búsqueda es exacta).
5. Interfaz. Hoy todo se usa desde la terminal.
