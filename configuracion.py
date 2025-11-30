# -*- coding: utf-8 -*-
"""
Nuevo configuracion.py — versión modular mínima
Encargado SOLO de:
- Crear menús
- Cargar módulos dinámicos desde el repositorio FI-UMH/Thonny
- Ejecutar los módulos cuando el usuario pulsa un menú

NO corrige ejercicios
NO descarga ficheros
NO manipula tests.json
"""

import sys
import urllib.request
import importlib.util
from thonny import get_workbench


# -------------------------------------------------------------------------
# CONFIGURACIÓN GENERAL
# -------------------------------------------------------------------------

# Repositorio unificado con todos los módulos
BASE_URL = "https://raw.githubusercontent.com/FI-UMH/Thonny/main/"


# -------------------------------------------------------------------------
# CARGADOR DINÁMICO DE MÓDULOS
# -------------------------------------------------------------------------

def cargar_o_importar(nombre_modulo):
    """
    Carga un módulo desde el repositorio FI-UMH/Thonny.
    Si ya está en sys.modules, NO lo descarga de nuevo.

    Devuelve el módulo preparado y ejecutado.
    """
    # Si ya está en memoria -> usamos el existente
    if nombre_modulo in sys.modules:
        return sys.modules[nombre_modulo]

    # Descargar el módulo .py del repositorio
    url = BASE_URL + nombre_modulo + ".py"

    try:
        with urllib.request.urlopen(url) as resp:
            codigo = resp.read().decode("utf-8")
    except Exception as e:
        print(f"[configuracion] Error descargando {url}: {e}")
        return None

    # Crear módulo en memoria
    spec = importlib.util.spec_from_loader(nombre_modulo, loader=None)
    mod = importlib.util.module_from_spec(spec)

    # Registrar módulo para futuras llamadas
    sys.modules[nombre_modulo] = mod

    # Ejecutar el código dentro del módulo
    try:
        exec(codigo, mod.__dict__)
    except Exception as e:
        print(f"[configuracion] Error ejecutando {nombre_modulo}.py: {e}")
        return None

    return mod


# -------------------------------------------------------------------------
# CREACIÓN DE MENÚS
# -------------------------------------------------------------------------

def _crear_menus():
    wb = get_workbench()
    menu = wb.get_menu("tools")

    if not menu:
        wb.after(600, _crear_menus)
        return

    # Acción del menú "Descargar ficheros"
    def accion_descargar_ficheros():
        mod = cargar_o_importar("descargar_ficheros")
        if mod and hasattr(mod, "main"):
            mod.main()

    # Acción del menú "Corregir ejercicio"
    def accion_corregir_ejercicio():
        mod = cargar_o_importar("corregir_ejercicio")
        if mod and hasattr(mod, "main"):
            mod.main()

    # Añadir menús
    menu.add_separator()
    menu.add_command(label="📥 Descargar ficheros", command=accion_descargar_ficheros)
    menu.add_command(label="✅ Corregir ejercicio", command=accion_corregir_ejercicio)


# -------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL
# -------------------------------------------------------------------------

def configurar(modulo):
    """
    Punto de entrada llamado por descargar_configuracion.py.
    'modulo' es el módulo temporal donde se ejecutó configuracion.py
    (se mantiene para compatibilidad futura).
    """
    _crear_menus()
