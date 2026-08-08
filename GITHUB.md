# Subir Lacancito a GitHub

Guía paso a paso, escrita para alguien que nunca usó GitHub.

---

## Antes que nada: qué es y qué no es GitHub

GitHub **guarda el código**. No lo ejecuta. Es un archivador con historial, no
un servidor donde la página quede andando.

Eso significa que subirlo a GitHub **no pone la app en internet**. Para que
alguien entre a una dirección y la use hacen falta dos cosas separadas:

1. **GitHub** guarda el programa. (Esta guía.)
2. Un **servicio que corra Python** lo pone a andar. (Al final, sección 7.)

Se puede hacer sólo el paso 1 y ya sirve: tenés el trabajo respaldado, con
historial, y cualquiera puede bajarlo y correrlo en su máquina.

---

## 1. Lo que NUNCA se sube

Lee esto aunque saltees el resto.

| No subir | Por qué |
|---|---|
| `datos/lacancito.db` | Tiene el texto completo de Lacan. Subirlo es publicarlo. |
| `datos/lacancito_publica.db` | No tiene texto, pero pesa 97 MB y GitHub rechaza archivos de más de 100 MB. |
| `datos/figuras/` | Son recortes de las páginas de los libros. |
| PDF, docx, epub | Obvio. |

El archivo `.gitignore` que ya está en la carpeta se encarga de excluir todo
eso automáticamente. **No lo borres ni lo edites** salvo que sepas lo que
hacés.

Lo que sí se sube: el código (`app.py`, `buscar.py`, `ingesta/`), el manual, los
`.bat` y los dos archivos de correcciones a mano.

Quien baje el repositorio no recibe ni una línea de Lacan. Recibe las
herramientas para armar la base **con sus propios libros**. Ésa es la
diferencia que hace que esto sea publicable.

---

## 2. Crear la cuenta e instalar Git

1. Entrá a **github.com** y creá una cuenta si no tenés.
2. Bajá **Git para Windows** de `git-scm.com/download/win` e instalalo. Dale
   *Siguiente* a todo; los valores por defecto están bien.
3. Reiniciá la terminal si tenías una abierta.

Para comprobar que quedó instalado, abrí una terminal en la carpeta
`lacancito` y escribí:

```bash
git --version
```

Si responde un número de versión, está listo.

---

## 3. Decirle a Git quién sos

Una sola vez en la vida, no una vez por proyecto:

```bash
git config --global user.name "Waldo Karakas Garcilaso"
```

```bash
git config --global user.email "tu-correo@ejemplo.com"
```

Usá el mismo correo con el que te registraste en GitHub.

---

## 4. Preparar la carpeta

Parada en `C:\Users\Waldo\Desktop\lacancito`:

```bash
git init -b main
```

```bash
git add .
```

Antes de seguir, **comprobá que no se coló nada pesado**. Este comando lista lo
que está por subirse, de mayor a menor tamaño:

```bash
git ls-files -s | awk '{print $4}' | xargs -I{} du -k "{}" | sort -rn | head -15
```

Si aparece algún `.db`, algún `.pdf` o algo de más de 1.000 KB, **pará** y
avisame antes de continuar. Si todo lo que ves son archivos de unos pocos KB,
seguí:

```bash
git commit -m "Lacancito: buscador de citas de Lacan"
```

---

## 5. Crear el repositorio en GitHub

1. En github.com, arriba a la derecha, **+** → **New repository**.
2. Nombre: `lacancito`
3. Descripción: *Buscador de citas de Lacan con referencia verificable*
4. Elegí **Public** si querés que se vea, o **Private** si preferís empezar
   guardado y decidir después. Se puede cambiar cuando quieras.
5. **No** marques ninguna de las casillas de abajo (`README`, `.gitignore`,
   `license`): ya los tenemos acá y chocarían.
6. **Create repository**.

---

## 6. Subirlo

GitHub te va a mostrar unos comandos. Usá estos, cambiando `TU-USUARIO`:

```bash
git remote add origin https://github.com/TU-USUARIO/lacancito.git
```

```bash
git push -u origin main
```

La primera vez se abre una ventana del navegador para que autorices. Aceptás y
listo.

De ahí en más, cada vez que cambies algo y lo quieras guardar:

```bash
git add . && git commit -m "qué cambié" && git push
```

---

## 7. Ponerla realmente en internet

GitHub no corre Python. **GitHub Pages tampoco**: sólo sirve páginas estáticas,
y Lacancito necesita un programa andando que consulte la base.

Hace falta un servicio de los que corren Python. Los que suelen tener plan
gratuito: **Render**, **Railway**, **Fly.io**, **PythonAnywhere**. Casi todos se
conectan directamente al repositorio de GitHub y se actualizan solos cuando
subís cambios.

Dos cosas a resolver ahí, y conviene saberlas antes de empezar:

**La base no está en el repositorio**, así que hay que subirla aparte al
servidor, o publicarla como *Release* de GitHub (los Release aceptan hasta 2 GB)
y que el servidor la baje al arrancar.

**Sólo se sube la pública.** `datos/lacancito_publica.db`, nunca la otra. La app
se da cuenta sola de cuál le tocó y se comporta en consecuencia, pero eso no
sustituye a fijarse.

---

## Si algo sale mal

**«fatal: not a git repository»** — no estás parada en la carpeta correcta.
Volvé a `C:\Users\Waldo\Desktop\lacancito`.

**«file is 97.41 MB; this exceeds GitHub's file size limit»** — se coló una
base. Se saca del envío con:

```bash
git rm --cached datos/lacancito_publica.db
```

y después se vuelve a hacer el `commit`.

**Subiste algo que no querías y ya está en GitHub** — borrar el archivo en un
commit nuevo **no lo saca del historial**: sigue estando y se puede recuperar.
Hay que reescribir el historial o borrar el repositorio y empezar de nuevo.
Por eso vale la pena el paso 4, mirar la lista antes de subir.
