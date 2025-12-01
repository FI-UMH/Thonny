# -*- coding: utf-8 -*-
"""
corregir_ejercicio.py
Versión final para FI-UMH/Thonny

Este módulo:
- Descarga tests.json (solo la primera vez)
- Corrige ejercicios pXXX (programa)
- Corrige ejercicios fXXX (funciones)
- Muestra error SOLO en el primer test fallado
- Válido para Thonny 4.x
"""

import sys
import os
import re
import json
import urllib.request
import tempfile
import subprocess
import importlib.util
import io
from contextlib import redirect_stdout
from unittest.mock import patch
from thonny import get_workbench
from tkinter import messagebox, Toplevel, Text, Scrollbar
import tkinter.font as tkfont
import re

# -------------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------------

TESTS_URL = "https://raw.githubusercontent.com/FI-UMH/Thonny/main/tests.json"
_PAREN_RE = re.compile(r"\([^()]*\)")
_TESTS_CACHE = None


# -------------------------------------------------------------------------
# UTILIDADES DE INTERFAZ
# -------------------------------------------------------------------------

def _mostrar_error_scroll(titulo, mensaje):
    win = Toplevel()
    win.title(titulo)
    win.geometry("820x520")

    txt = Text(win, wrap="none", font=("Consolas", 10))
    txt.pack(fill="both", expand=True)

    sy = Scrollbar(win, orient="vertical", command=txt.yview)
    sy.pack(side="right", fill="y")
    txt.configure(yscrollcommand=sy.set)

    sx = Scrollbar(win, orient="horizontal", command=txt.xview)
    sx.pack(side="bottom", fill="x")
    txt.configure(xscrollcommand=sx.set)

    txt.insert("1.0", mensaje)

    base = tkfont.Font(font=txt["font"])
    bold = base.copy()
    bold.configure(weight="bold")
    txt.tag_configure("titulo", font=bold)

    for palabra in ("CONTEXTO INICIAL", "RESULTADO OBTENIDO", "RESULTADO CORRECTO"):
        start = "1.0"
        while True:
            pos = txt.search(palabra, start, stopindex="end")
            if not pos:
                break
            end = f"{pos}+{len(palabra)}c"
            txt.tag_add("titulo", pos, end)
            start = end

    txt.config(state="disabled")


# -------------------------------------------------------------------------
# TESTS
# -------------------------------------------------------------------------

def _descargar_tests():
    global _TESTS_CACHE
    if _TESTS_CACHE is not None:
        return _TESTS_CACHE

    try:
        with urllib.request.urlopen(TESTS_URL, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            _TESTS_CACHE = json.loads(data)
            return _TESTS_CACHE
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo descargar tests.json:\n{e}")
        return None  # <<--- IMPORTANTE


# -------------------------------------------------------------------------
# UTILIDADES DE EJECUCIÓN
# -------------------------------------------------------------------------

def _decode_bytes(b: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return b.decode(enc)
        except:
            pass
    return b.decode("utf-8", errors="replace")


def _paren_counter(s: str):
    raw = _PAREN_RE.findall(s or "")
    norm = [ "(" + re.sub(r"\s+", "", tok[1:-1]) + ")" for tok in raw ]
    from collections import Counter
    return Counter(norm)


def _extraer_ejercicio_y_dni(codigo):
    dni_m = re.search(r"^\s*#\s*DNI\s*=\s*(.+)$", codigo, re.MULTILINE)
    ej_m  = re.search(r"^\s*#\s*EJERCICIO\s*=\s*(.+)$", codigo, re.MULTILINE)
    dni = dni_m.group(1).strip() if dni_m else None
    ej  = ej_m.group(1).strip() if ej_m else None
    return dni, ej


def _preprocesar_codigo(src: str) -> str:
    src_mod = re.sub(r"input\s*\(", "inputt(", src)
    cabecera = (
        "def inputt(msg=''):\n"
        "    x = input(msg)\n"
        "    print(x)\n"
        "    return x\n\n"
    )
    return cabecera + src_mod

def comparar_resultados_pantalla(pantalla_obtenida: str, pantalla_correcta: str):
    patron = r"\((.*?)\)"

    obt_abre = pantalla_obtenida.count("(")
    obt_cierra = pantalla_obtenida.count(")")
    cor_abre = pantalla_correcta.count("(")
    cor_cierra = pantalla_correcta.count(")")

    diferencias = []

    # Paréntesis desbalanceados
    if obt_abre != obt_cierra:
        diferencias.append(f"Paréntesis desbalanceados en la salida obtenida: {obt_abre} '(' vs {obt_cierra} ')'.")
        return False, diferencias

    if cor_abre != cor_cierra:
        diferencias.append(f"Paréntesis desbalanceados en la salida correcta: {cor_abre} '(' vs {cor_cierra} ')'.")
        return False, diferencias

    # Conteo distinto
    if obt_abre != cor_abre:
        diferencias.append(f"Número de resultados distinto. Obtenida: {obt_abre}, Correcta: {cor_abre}.")

    # Extraer resultados
    res_obtenidos = [r.replace(" ", "") for r in re.findall(patron, pantalla_obtenida)]
    res_correctos = [r.replace(" ", "") for r in re.findall(patron, pantalla_correcta)]

    # Comparación sin orden
    faltan = [rc for rc in res_correctos if rc not in res_obtenidos]

    if faltan:
        diferencias.append(f"Faltan resultados: {faltan}")
        diferencias.append(f"Obtenidos: {res_obtenidos}")
        diferencias.append(f"Correctos: {res_correctos}")
        return False, diferencias

    return True, []

def comparar_ficheros(ficheros_obtenidos: dict, ficheros_correctos: dict):
    diferencias = []

    # 1. Comparar nombres
    nombres_obtenidos = set(ficheros_obtenidos.keys())
    nombres_correctos = set(ficheros_correctos.keys())

    faltan = nombres_correctos - nombres_obtenidos
    sobran = nombres_obtenidos - nombres_correctos

    if faltan:
        diferencias.append(f"Faltan ficheros: {sorted(list(faltan))}")
    if sobran:
        diferencias.append(f"Ficheros inesperados: {sorted(list(sobran))}")

    # Si ya fallan los nombres no hace falta seguir
    if diferencias:
        return False, diferencias

    # 2. Comparar contenido
    for nombre in nombres_correctos:
        if ficheros_obtenidos[nombre] != ficheros_correctos[nombre]:
            diferencias.append(f"El contenido del fichero '{nombre}' es diferente.")

    if diferencias:
        return False, diferencias

    return True, []

# -------------------------------------------------------------------------
# CORRECCIÓN DE PROGRAMAS pXXX
# -------------------------------------------------------------------------

def corregir_ejercicio_programa(codigo, ejercicio, lista_tests):

    for test in lista_tests:

        # Ejecutar programa del alumno
        salida, files_ini_text, files_fin_text = ejecutar_programa(codigo, test)

        pantalla_obtenida = salida.get("stdout", "")
        pantalla_correcta = test.get("stdout", "")

        # Comparación de pantalla
        ok_pantalla, dif_pantalla = comparar_resultados_pantalla(
            pantalla_obtenida,
            pantalla_correcta
        )

        # Comparación de ficheros
        ok_ficheros, dif_ficheros = comparar_ficheros(
            files_fin_text,
            test.get("files", {})
        )

        if ok_pantalla and ok_ficheros:
            continue  # siguiente test

        # Preparar diferencias
        diferencias_detectadas = "\n".join(dif_pantalla + dif_ficheros)

        msg = (
            "El ejercicio no supera el test\n\n"
            f"{diferencias_detectadas}\n\n"
            "▶ CONTEXTO INICIAL\n"
            "─────── Teclado ───────\n"
            f"{test.get('stdin', '')}\n"
            "─────── Ficheros ───────\n"
            f"{files_ini_text}\n\n"
            "▶ RESULTADO OBTENIDO\n"
            "─────── Pantalla ───────\n"
            f"{pantalla_obtenida}\n"
            "─────── Ficheros ───────\n"
            f"{files_fin_text}\n\n"
            "▶ RESULTADO CORRECTO\n"
            "─────── Pantalla ───────\n"
            f"{pantalla_correcta}\n"
            "─────── Ficheros ───────\n"
            f"{test.get('files_text', '')}\n"
        )

        mostrar_error_scroll("Resultado de la corrección", msg)
        return  # se detiene en el primer fallo

    mostrar_info("Resultado de la corrección", "El ejercicio supera todos los tests.")



# -------------------------------------------------------------------------
# CORRECCIÓN DE FUNCIONES fXXX
# -------------------------------------------------------------------------

def corregir_ejercicio_funciones(codigo, ejercicio, lista_tests):

    for test in lista_tests:

        # Ejecutar la función del alumno
        try:
            salida = ejecutar_funcion(
                codigo,
                test["function"],
                test.get("args", []),
                test.get("kwargs", {})
            )
        except Exception as e:
            msg = (
                "El ejercicio no supera el test\n\n"
                f"Error al ejecutar la función: {e}\n\n"
                "▶ CONTEXTO INICIAL\n"
                f"Función: {test['function']}\n"
                f"Args: {test.get('args', [])}\n"
                f"Kwargs: {test.get('kwargs', {})}\n"
            )
            mostrar_error_scroll("Resultado de la corrección", msg)
            return

        pantalla_obtenida = salida.get("stdout", "")
        valor_obtenido = salida.get("return", None)

        pantalla_correcta = test.get("stdout", "")
        valor_correcto = test.get("return", None)

        # Comparación de pantalla
        ok_pantalla, dif_pantalla = comparar_resultados_pantalla(
            pantalla_obtenida,
            pantalla_correcta
        )

        # Comparación de valor de retorno
        ok_valor = (valor_obtenido == valor_correcto)
        dif_valor = []

        if not ok_valor:
            dif_valor.append(
                f"Valor retornado incorrecto. Obtenido: {valor_obtenido}, Correcto: {valor_correcto}"
            )

        if ok_pantalla and ok_valor:
            continue  # siguiente test

        # Montar diferencias
        diferencias_detectadas = "\n".join(dif_pantalla + dif_valor)

        msg = (
            f"La función NO supera el test {idx}.\n\n"
            "DIFERENCIAS DETECTADAS:\n"
            + "\n".join(diferencias_detectadas)
            + "\n\n"
            f"FUNCION: {func}\n"
            f"ARGUMENTOS: {args}\n\n"
            "▶ CONTEXTO INICIAL\n"
            "─────── Teclado ───────\n"
            f"{stdin_val}\n"
            "─────── Ficheros ───────\n"
            + "\n".join(f"{k} → {v}" for k, v in filesIni.items()) + "\n\n"
            "▶ RESULTADO OBTENIDO\n"
            "─────── return ───────\n"
            f"{ret_obt!r}\n"
            "─────── Pantalla ───────\n"
            f"{stdout_obt}\n"
            "─────── Ficheros ───────\n"
            + "\n".join(f"{k} → {v}" for k, v in files_end.items()) + "\n\n"
            "▶ RESULTADO CORRECTO\n"
            "─────── return ───────\n"
            f"{ret_exp!r}\n"
            "─────── Pantalla ───────\n"
            f"{stdout_exp}\n"
            "─────── Ficheros ───────\n"
            + "\n".join(f"{k} → {v}" for k, v in filesEnd_exp.items())
        )

        mostrar_error_scroll("Resultado de la corrección", msg)
        return

    mostrar_info("Resultado de la corrección", "El ejercicio supera todos los tests.")



# -------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL
# -------------------------------------------------------------------------

def main():
    wb = get_workbench()
    ed = wb.get_editor_notebook().get_current_editor()

    if not ed:
        messagebox.showerror("Error", "No hay ningún editor activo.")
        return

    try:
        codigo = ed.get_text_widget().get("1.0", "end-1c")
    except:
        codigo = ""

    dni, ejercicio = _extraer_ejercicio_y_dni(codigo)

    if not ejercicio:
        messagebox.showerror("Error", "No se encontró '# EJERCICIO =' en la cabecera.")
        return

    tests = _descargar_tests()
    if not tests or ejercicio not in tests:
        messagebox.showerror("Error", f"No existen tests para el ejercicio {ejercicio}.")
        return

    lista = tests[ejercicio]

    if ejercicio.startswith("p"):
        _corregir_programa(codigo, ejercicio, lista)
    elif ejercicio.startswith("f"):
        _corregir_funcion(codigo, ejercicio, lista)
    else:
        messagebox.showerror("Error", "El ejercicio debe empezar por 'p' o 'f'.")
