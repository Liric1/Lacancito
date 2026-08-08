# Cómo poner Lacancito a andar

Escrito para alguien que no programa. Son cuatro pasos y se hacen una sola vez.

---

## Lo primero que hay que entender

**Este repositorio no trae los textos de Lacan.** Sólo trae el programa. La
base de datos se arma en tu propia máquina, a partir de los PDF que vos tengas.

Sin esos PDF, la app abre y no encuentra nada. No está rota: le falta el
material.

Hay dos maneras de conseguir la base:

- **Armarla vos**, con tus propios archivos. Es lo que explica esta guía.
- **Que alguien te pase el archivo `lacancito.db` ya hecho.** En ese caso saltá
  al final, a *«Si te pasaron la base ya hecha»*.

---

## 1. Instalar Python

Bajalo de **python.org/downloads** e instalalo.

En la primera pantalla del instalador hay una casilla abajo que dice **«Add
python.exe to PATH»**. **Marcala.** Si no, los comandos de después no van a
funcionar y el error no dice por qué.

Para comprobar que quedó, abrí una terminal —tecla Windows, escribí `cmd`,
Enter— y escribí:

```bash
python --version
```

Tiene que responder un número. Si dice que no reconoce el comando, volvé a
instalar Python con la casilla marcada.

---

## 2. Bajar Lacancito

En **github.com/Liric1/Lacancito**, botón verde **Code** → **Download ZIP**.

Descomprimí el ZIP donde quieras. Va a quedar una carpeta con `app.py`,
`Lacancito.bat` y una carpeta `ingesta`.

---

## 3. Instalar la pieza que falta

Abrí una terminal **dentro de esa carpeta**. La forma rápida en Windows: entrá
a la carpeta, hacé clic en la barra de dirección de arriba, escribí `cmd` y
Enter.

```bash
python -m pip install pymupdf
```

Es la única dependencia. Tarda menos de un minuto.

---

## 4. Armar la base con tus PDF

Necesitás tus seminarios de Lacan en PDF, todos en una misma carpeta, con
nombres que empiecen con `S` y el número: `S1 ...pdf`, `S20 ENCORE.pdf`, etc.

Después, tres comandos. Reemplazá `RUTA A TUS SEMINARIOS` por la ruta real
—se copia de la barra de dirección del explorador— y dejá las comillas:

```bash
python ingesta/ingestar_todos.py "RUTA A TUS SEMINARIOS"
```

```bash
python ingesta/fuentes.py --carpeta "RUTA A TUS SEMINARIOS"
```

```bash
python ingesta/indexar_fonetica.py
```

El primero tarda varios minutos y va mostrando cada seminario a medida que lo
procesa. El tercero tarda unos tres minutos y no muestra casi nada: es normal.

Si además tenés los *Écrits* o los *Autres écrits* escaneados en PDF, se agregan
con `ingesta/ingestar_escritos.py`; está explicado en `LEEME.md`.

---

## 5. Usarlo

**Doble clic en `Lacancito.bat`.**

Se abre una ventana negra —dejala abierta, es el motor— y enseguida el
navegador con la página. Para cerrar todo, cerrás la ventana negra.

---

## Si te pasaron la base ya hecha

Poné el archivo `lacancito.db` dentro de la carpeta `datos` y hacé doble clic
en `Lacancito.bat`. Nada más. Igual necesitás los pasos 1 y 3 —Python y
pymupdf—, pero te salteás el 4, que es el largo.

---

## Si la ventana negra se abre y se cierra sola

Se cierra después de mostrar un error. Para leerlo, abrí la terminal en la
carpeta y escribí `python app.py`: ahí el mensaje queda a la vista.

Los dos errores típicos:

**«No encuentro la base de datos»** — falta el paso 4, o el archivo
`lacancito.db` no está en la carpeta `datos`.

**«No module named pymupdf»** — falta el paso 3.
