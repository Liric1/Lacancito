# Lacancito

Buscador de citas de Lacan con referencia verificable: obra, clase, fecha,
página y edición.

Hecho por **Waldo Karakas Garcilaso** ·
[lance.tiiny.site](https://lance.tiiny.site/) ·
[@waldokg.psa](https://www.instagram.com/waldokg.psa/)

---

## Qué hace

- **Texto exacto**, sin necesidad de poner los acentos.
- **Por cómo suena.** Lacan hace equívocos por homofonía: `les non-dupes errent`
  y `le Nom-du-Père` suenan igual y no comparten una letra en el mismo orden.
  Un buscador de texto no puede relacionarlas; éste sí, porque guarda de cada
  fragmento cómo se pronuncia.
- **Palabras cerca** una de otra, a la distancia que se elija. `jouissance
  femme` como frase exacta no aparece nunca; a diez palabras aparece 69 veces.
- **Análisis**: frecuencia relativa por año, acumulado, reparto por obra,
  primera y última aparición, concentración. Hasta tres términos superpuestos.
- **Ver la página original** del PDF, para verificar una cita contra el papel.
- Cada resultado da la **cita en APA** con la edición de la que salió, y un
  enlace para abrir el pasaje en un traductor.

## Este repositorio no contiene textos de Lacan

Sólo el programa. La base se arma en la propia máquina, a partir de los libros
que cada uno tenga. Sin esos archivos, lo que se baja de acá no sirve para leer
a Lacan: sirve para indexar los libros de uno.

## Cómo se usa

Hace falta **Python 3.10 o más nuevo** y una sola dependencia:

```bash
python -m pip install pymupdf
```

Después, armar la base a partir de los PDF propios:

```bash
python ingesta/ingestar_todos.py "RUTA\A\LOS\SEMINARIOS" --db datos/lacancito.db
python ingesta/fuentes.py --carpeta "RUTA\A\LOS\SEMINARIOS" --db datos/lacancito.db
python ingesta/indexar_fonetica.py --db datos/lacancito.db
```

Y abrir la app:

```bash
python app.py
```

En Windows alcanza con hacer doble clic en `Lacancito.bat`.

El detalle de cada paso, de dónde sale cada número de página y qué está
verificado y qué no, está en [LEEME.md](LEEME.md). Para publicarlo,
[GITHUB.md](GITHUB.md).

## Licencia

El código, MIT. Los textos de Lacan no son míos ni están acá.
