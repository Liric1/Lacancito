# -*- coding: utf-8 -*-
"""
Corre el ingestor sobre todos los seminarios de una carpeta y reporta el estado
de cada uno. Si algun seminario tiene un problema, aparece marcado con !!

Uso:
    python ingestar_todos.py "C:\\...\\0LACAN" --db datos\\lacancito.db
"""
import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingestar_seminario import ingestar, guardar  # noqa: E402

TITULOS = {
    "1": "Los escritos técnicos de Freud", "2": "El yo", "3": "Las psicosis",
    "4": "La relación de objeto", "5": "Las formaciones del inconsciente",
    "6": "El deseo y su interpretación", "7": "La ética del psicoanálisis",
    "8": "La transferencia", "9": "La identificación", "10": "La angustia",
    "11": "Los cuatro conceptos fundamentales", "12": "Problemas cruciales",
    "13": "El objeto del psicoanálisis", "14": "La lógica del fantasma",
    "15": "El acto psicoanalítico", "16": "De un Otro al otro",
    "17": "El reverso del psicoanálisis", "18": "De un discurso que no fuera del semblante",
    "19": "…O peor", "19b": "El saber del psicoanalista", "20": "Aún",
    "21": "Los no incautos yerran", "22": "R.S.I.", "23": "El sinthome",
    "24": "L'insu que sait de l'une-bévue", "25": "El momento de concluir",
    "26": "La topología y el tiempo", "27": "Disolución",
}


def nombre_obra(ruta):
    base = os.path.splitext(os.path.basename(ruta))[0]
    m = re.match(r"S\s*(\d+b?)\b", base, re.I)
    if not m:
        return base
    n = m.group(1).lower()
    titulo = TITULOS.get(n)
    return f"Seminario {n}" + (f" — {titulo}" if titulo else "")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    pdfs = sorted(glob.glob(os.path.join(args.carpeta, "S*.pdf")),
                  key=lambda p: (int(re.match(r"S\s*(\d+)", os.path.basename(p), re.I).group(1))
                                 if re.match(r"S\s*(\d+)", os.path.basename(p), re.I) else 999,
                                 os.path.basename(p)))
    if not pdfs:
        print(f"No encontre PDF que empiecen con 'S' en {args.carpeta}")
        return

    print(f"{'OBRA':<48} {'SES':>7} {'FRAG':>6} {'CARACTERES':>12}  ESTADO")
    print("-" * 96)
    total_frag = total_car = 0
    problemas = []

    for pdf in pdfs:
        obra = nombre_obra(pdf)
        try:
            sesiones, segs, declaradas = ingestar(pdf, obra)
        except Exception as e:                      # noqa: BLE001
            print(f"{obra:<48} {'-':>7} {'-':>6} {'-':>12}  !! ERROR: {e}")
            problemas.append((obra, f"error: {e}"))
            continue

        lacan = [s for s in segs if s["capa"] == "lacan"]
        car = sum(len(s["texto"]) for s in lacan)
        encontradas = {iso for _, iso, _ in sesiones}
        faltan = sorted(set(declaradas) - encontradas)

        estado = "ok"
        if not lacan:
            estado = "!! SIN TEXTO DE CUERPO"
        elif faltan:
            estado = f"!! faltan sesiones: {', '.join(faltan)}"
        elif not declaradas:
            estado = "sin tabla de sesiones (no se pudo verificar)"
        if estado != "ok":
            problemas.append((obra, estado))

        print(f"{obra:<48} {len(sesiones):>3}/{len(declaradas):<3} "
              f"{len(lacan):>6} {car:>12,}  {estado}")
        total_frag += len(lacan)
        total_car += car

        if args.db and segs:
            guardar(segs, args.db)

    print("-" * 96)
    print(f"{'TOTAL':<48} {'':>7} {total_frag:>6} {total_car:>12,}")
    if problemas:
        print(f"\n{len(problemas)} obra(s) requieren revisión:")
        for obra, est in problemas:
            print(f"   - {obra}: {est}")
    if args.db:
        print(f"\nBase de datos: {args.db}")


if __name__ == "__main__":
    main()
