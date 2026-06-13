#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprime un video MP4 a WebM (VP9 + Opus) optimizado para web.

- Pensado para grabaciones de carretera (mucho movimiento).
- Doble pasada + calidad constante (CRF) => menor tamaño sin pérdida visible.
- Guarda el resultado en la carpeta raíz del proyecto (junto a este script).

Requisito: tener ffmpeg instalado y accesible en el PATH.
  - Windows:  winget install Gyan.FFmpeg     (o https://www.gyan.dev/ffmpeg/builds/)
  - macOS:    brew install ffmpeg
  - Linux:    sudo apt install ffmpeg

Uso:
    python comprimir_video_webm.py
"""

import os
import sys
import shutil
import subprocess

# Carpeta raíz del proyecto = carpeta donde está este script
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Perfiles de calidad: (crf, audio_kbps, descripcion)
# CRF más bajo = mejor calidad y más peso. Para web, 33-36 suele ser el punto dulce.
PERFILES = {
    "1": (30, 128, "Máxima calidad (archivo más grande)"),
    "2": (33, 96,  "Alta calidad (recomendado)"),
    "3": (36, 96,  "Optimizado para web (más ligero)"),
}


def comprobar_ffmpeg():
    """Verifica que ffmpeg esté disponible."""
    if shutil.which("ffmpeg") is None:
        print("\n[ERROR] No se encontró 'ffmpeg' en el sistema.")
        print("Instálalo y vuelve a ejecutar el script:")
        print("  - Windows: winget install Gyan.FFmpeg")
        print("  - macOS:   brew install ffmpeg")
        print("  - Linux:   sudo apt install ffmpeg")
        sys.exit(1)


def pedir_ruta():
    """Pide la ruta del video y la valida."""
    ruta = input("Ruta del video MP4: ").strip().strip('"').strip("'")
    ruta = os.path.expanduser(ruta)
    if not os.path.isfile(ruta):
        print(f"\n[ERROR] No existe el archivo: {ruta}")
        sys.exit(1)
    return ruta


def pedir_perfil():
    """Permite elegir el nivel de calidad. Enter = recomendado."""
    print("\nNivel de calidad:")
    for clave, (_, _, desc) in PERFILES.items():
        print(f"  {clave}) {desc}")
    opcion = input("Elige una opción [2]: ").strip() or "2"
    if opcion not in PERFILES:
        opcion = "2"
    crf, audio_kbps, desc = PERFILES[opcion]
    print(f"-> {desc}  (CRF {crf}, audio {audio_kbps}k)\n")
    return crf, audio_kbps


def pedir_resolucion():
    """Opcional: limitar la altura máxima (útil para web). Enter = original."""
    print("Altura máxima de salida (para web, 1080 va muy fluido).")
    valor = input("Pixeles [Enter = mantener original]: ").strip()
    if valor.isdigit():
        return int(valor)
    return None


def ruta_salida(ruta_entrada):
    """Genera la ruta de salida en la raíz del proyecto, sin sobrescribir."""
    base = os.path.splitext(os.path.basename(ruta_entrada))[0]
    salida = os.path.join(PROJECT_ROOT, base + ".webm")
    contador = 1
    while os.path.exists(salida):
        salida = os.path.join(PROJECT_ROOT, f"{base}_{contador}.webm")
        contador += 1
    return salida


def construir_filtros(max_altura):
    """Escala manteniendo la proporción solo si hace falta reducir."""
    if max_altura:
        # -2 mantiene la proporción y asegura dimensiones pares (requisito de VP9)
        return ["-vf", f"scale=-2:'min({max_altura},ih)'"]
    return []


def comprimir(entrada, salida, crf, audio_kbps, max_altura):
    hilos = str(os.cpu_count() or 4)
    null_dev = "NUL" if os.name == "nt" else "/dev/null"
    log_prefix = os.path.join(PROJECT_ROOT, "ffmpeg2pass")
    filtros = construir_filtros(max_altura)

    # Parámetros de calidad VP9 (buenos para vídeo con mucho movimiento)
    base_vp9 = [
        "-c:v", "libvpx-vp9",
        "-b:v", "0",            # 0 + crf = modo calidad constante
        "-crf", str(crf),
        "-row-mt", "1",         # multihilo por filas
        "-tile-columns", "2",
        "-threads", hilos,
        "-g", "240",            # intervalo de keyframes
        "-pix_fmt", "yuv420p",  # máxima compatibilidad en navegadores
    ]

    # --- PASADA 1 (analiza, sin audio, salida descartada) ---
    pase1 = (
        ["ffmpeg", "-y", "-i", entrada]
        + filtros
        + base_vp9
        + ["-cpu-used", "4",    # rápido en la 1ª pasada
           "-pass", "1", "-passlogfile", log_prefix,
           "-an", "-f", "webm", null_dev]
    )

    # --- PASADA 2 (calidad final, con audio Opus) ---
    pase2 = (
        ["ffmpeg", "-y", "-i", entrada]
        + filtros
        + base_vp9
        + ["-cpu-used", "1",    # más lento = mejor compresión/calidad
           "-pass", "2", "-passlogfile", log_prefix,
           "-c:a", "libopus", "-b:a", f"{audio_kbps}k",
           salida]
    )

    print("== Pasada 1/2 (análisis) ==")
    subprocess.run(pase1, check=True)
    print("\n== Pasada 2/2 (codificación final) ==")
    subprocess.run(pase2, check=True)

    # Limpieza de los logs temporales de la doble pasada
    for f in os.listdir(PROJECT_ROOT):
        if f.startswith("ffmpeg2pass"):
            try:
                os.remove(os.path.join(PROJECT_ROOT, f))
            except OSError:
                pass


def mb(ruta):
    return os.path.getsize(ruta) / (1024 * 1024)


def main():
    print("=== Compresor MP4 -> WebM (VP9) para web ===\n")
    comprobar_ffmpeg()
    entrada = pedir_ruta()
    crf, audio_kbps = pedir_perfil()
    max_altura = pedir_resolucion()
    salida = ruta_salida(entrada)

    print(f"\nEntrada : {entrada}  ({mb(entrada):.1f} MB)")
    print(f"Salida  : {salida}\n")

    try:
        comprimir(entrada, salida, crf, audio_kbps, max_altura)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] ffmpeg falló (código {e.returncode}).")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")
        sys.exit(1)

    final = mb(salida)
    original = mb(entrada)
    ahorro = (1 - final / original) * 100 if original else 0
    print("\n=== Listo ===")
    print(f"Archivo: {salida}")
    print(f"Tamaño : {original:.1f} MB  ->  {final:.1f} MB  ({ahorro:.0f}% menos)")


if __name__ == "__main__":
    main()
