# -*- coding: utf-8 -*-
"""
Baja la base durante la CONSTRUCCIÓN del servidor, no al arrancar.

Por qué importa la diferencia. En un plan gratuito el servicio se apaga cuando
nadie lo usa y vuelve a arrancar en la visita siguiente. Lo que se escribe
mientras corre se pierde en cada apagón; lo que queda de la construcción, no.
Si la descarga de 156 MB pasa al arrancar, cada usuario que llega después de un
rato de inactividad la espera entera. Si pasa en la construcción, se hace una
vez por despliegue y el arranque es inmediato.

Se usa como comando de construcción:

    pip install -r requirements.txt && python descargar_base.py

Si no hay LACANCITO_DB_URL definida, no hace nada y no falla: así el mismo
comando sirve en una computadora, donde la base ya está.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from buscar import DB  # noqa: E402
from app import bajar_base_si_falta  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not os.environ.get("LACANCITO_DB_URL"):
        print("Sin LACANCITO_DB_URL: no hay nada que bajar.")
        sys.exit(0)
    bajar_base_si_falta(DB)
    if os.path.exists(DB):
        print(f"Base en su lugar: {os.path.getsize(DB) / 1e6:.0f} MB")
    else:
        sys.exit("No se pudo dejar la base en su lugar.")
