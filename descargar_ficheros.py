# -*- coding: utf-8 -*-
"""
descargar_ficheros.py
----------------------------------------
Módulo descargado dinámicamente por configuracion.py.

Funciona así:
- Descarga el archivo ficheros.zip de FI-UMH/Thonny
- Descomprime su contenido en memoria
- Copia todos los ficheros a la carpeta elegida por el alumno

No crea archivos temporales en disco salvo los estrictamente utilizados
por zipfile (gestionados en memoria).
"""

import urllib.request
import zipfile
import io
import os
from tkinter import filedialog, messagebox


# -------------------------------------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------------------------------------

ZIP_URL = "https://raw.githubusercontent.com/FI-UMH/Thonny/main/ficheros.zip"


# -------------------------------------------------------------------------
# DESCARGA DEL ZIP
# -------------------------------------------------------------------------

def _descargar_zip() -> bytes:
    """Descarga ficheros.zip desde GitHub y devuelve su contenido como bytes."""
    try:
        with urllib.request.urlopen(ZIP_URL) as resp:
            return resp.read()
    except Exception as e:
        messagebox.showerror("Error", f"Error descargando ficheros.zip:\n{e}")
        return None


# -------------------------------------------------------------------------
# EXTRACCIÓN DEL ZIP
# -------------------------------------------------------------------------

def _extraer_zip(data: bytes, destino: str):
    """
    Extrae todos los archivos contenidos en ficheros.zip
    dentro de la carpeta destino elegida por el usuario.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for nombre in z.namelist():

                # Saltar directorios
                if nombre.endswith("/"):
                    continue

                contenido = z.read(nombre)

                ruta_salida = os.path.join(destino, nombre)

                # Crear directorios intermedios
                os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)

                # Escribir fichero final
                with open(ruta_salida, "wb") as f:
                    f.write(contenido)

        messagebox.showinfo("Descargar ficheros", "Ficheros descargados correctamente.")

    except Exception as e:
        messagebox.showerror("Error", f"Error extrayendo ficheros.zip:\n{e}")


# -------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL (llamada por configuracion.py)
# -------------------------------------------------------------------------

def main():
    """Función de entrada llamada por el menú 'Descargar ficheros'."""
    destino = filedialog.askdirectory(title="Selecciona carpeta destino")

    if not destino:
        return

    data = _descargar_zip()
    if data is None:
        return

    _extraer_zip(data, destino)

