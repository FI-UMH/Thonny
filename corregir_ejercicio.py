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


# -------------------------------------------------------------------------
# CORRECCIÓN DE PROGRAMAS pXXX
# -------------------------------------------------------------------------

def _corregir_programa(codigo, ejercicio, tests):
    aciertos = 0

    with tempfile.TemporaryDirectory() as tmp:
        ruta_mod = os.path.join(tmp, "alumno.py")
        with open(ruta_mod, "w", encoding="utf-8") as f:
            f.write(_preprocesar_codigo(codigo))

        for idx, test in enumerate(tests, 1):
            stdin_val = test["stdin"]
            files_ini = test["filesIni"]
            stdout_exp = test["stdout"]
            files_exp  = test["filesEnd"]

            with tempfile.TemporaryDirectory() as work:
                for nom, txt in files_ini.items():
                    ruta = os.path.join(work, nom)
                    os.makedirs(os.path.dirname(ruta) or work, exist_ok=True)
                    with open(ruta, "w", encoding="utf-8") as fw:
                        fw.write(txt)

                try:
                    completed = subprocess.run(
                        [sys.executable, ruta_mod],
                        cwd=work,
                        input=stdin_val.encode(),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=5
                    )
                except subprocess.TimeoutExpired:
                    _mostrar_error_scroll(
                        "Resultado de la corrección",
                        f"Tiempo excedido en el test {idx}"
                    )
                    return

                stdout_obt = _decode_bytes(completed.stdout)

                files_end = {}
                for nom in os.listdir(work):
                    p = os.path.join(work, nom)
                    if os.path.isfile(p):
                        with open(p, "r", encoding="utf-8", errors="replace") as fr:
                            files_end[nom] = fr.read()

            if _paren_counter(stdout_obt) != _paren_counter(stdout_exp) or files_end != files_exp:

                msg = (
                    f"El ejercicio NO supera el test {idx}.\n\n"
                    "▶ CONTEXTO INICIAL\n"
                    "─────── Teclado ───────\n"
                    f"{stdin_val}\n"
                    "─────── Ficheros ───────\n" +
                    "\n".join(f"{k} → {v}" for k, v in files_ini.items()) +
                    "\n\n"
                    "▶ RESULTADO OBTENIDO\n"
                    "─────── Pantalla ───────\n"
                    f"{stdout_obt}\n"
                    "─────── Ficheros ───────\n" +
                    "\n".join(f"{k} → {v}" for k, v in files_end.items()) +
                    "\n\n"
                    "▶ RESULTADO CORRECTO\n"
                    "─────── Pantalla ───────\n"
                    f"{stdout_exp}\n"
                    "─────── Ficheros ───────\n" +
                    "\n".join(f"{k} → {v}" for k, v in files_exp.items())
                )

                _mostrar_error_scroll("Resultado de la corrección", msg)
                return

            aciertos += 1

    messagebox.showinfo("Correcto", f"🎉 ¡Todos los tests ({aciertos}) superados correctamente!")


# -------------------------------------------------------------------------
# CORRECCIÓN DE FUNCIONES fXXX
# -------------------------------------------------------------------------

def _corregir_funcion(codigo, ejercicio, tests):
    aciertos = 0

    with tempfile.TemporaryDirectory() as tmp:
        ruta = os.path.join(tmp, "alumno.py")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(_preprocesar_codigo(codigo))

        spec = importlib.util.spec_from_file_location("alumno_mod", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        for idx, test in enumerate(tests, 1):
            func = test["funcName"]
            args = test["args"]
            stdin_val = test["stdin"]
            filesIni = test["filesIni"]
            ret_exp = test["return"]
            stdout_exp = test["stdout"]
            filesEnd_exp = test["filesEnd"]

            if not hasattr(mod, func):
                _mostrar_error_scroll("Resultado de la corrección",
                                      f"La función '{func}' no está definida por el alumno.")
                return

            func_al = getattr(mod, func)

            with tempfile.TemporaryDirectory() as work:
                for nom, txt in filesIni.items():
                    with open(os.path.join(work, nom), "w", encoding="utf-8") as fw:
                        fw.write(txt)

                stdin_io = io.StringIO(stdin_val)
                stdout_io = io.StringIO()

                def fake_input(msg=""):
                    return stdin_io.readline().rstrip("\n")

                cwd_old = os.getcwd()
                os.chdir(work)

                try:
                    with redirect_stdout(stdout_io), patch("builtins.input", fake_input):
                        ret_obt = func_al(*args)
                except Exception as e:
                    os.chdir(cwd_old)
                    _mostrar_error_scroll("Resultado de la corrección",
                                          f"Error ejecutando la función en el test {idx}:\n{e}")
                    return
                finally:
                    os.chdir(cwd_old)

                stdout_obt = stdout_io.getvalue()

                files_end = {}
                for nom in os.listdir(work):
                    with open(os.path.join(work, nom), "r", encoding="utf-8", errors="replace") as fr:
                        files_end[nom] = fr.read()

            if ret_obt != ret_exp or stdout_obt != stdout_exp or files_end != filesEnd_exp:

                msg = (
                    f"La función NO supera el test {idx}.\n\n"
                    f"FUNCION: {func}\n"
                    f"ARGUMENTOS: {args}\n\n"
                    "▶ CONTEXTO INICIAL\n"
                    "─────── Teclado ───────\n"
                    f"{stdin_val}\n"
                    "─────── Ficheros ───────\n" +
                    "\n".join(f"{k} → {v}" for k, v in filesIni.items()) +
                    "\n\n"
                    "▶ RESULTADO OBTENIDO\n"
                    "─────── return ───────\n"
                    f"{ret_obt!r}\n"
                    "─────── Pantalla ───────\n"
                    f"{stdout_obt}\n"
                    "─────── Ficheros ───────\n" +
                    "\n".join(f"{k} → {v}" for k, v in files_end.items()) +
                    "\n\n"
                    "▶ RESULTADO CORRECTO\n"
                    "─────── return ───────\n"
                    f"{ret_exp!r}\n"
                    "─────── Pantalla ───────\n"
                    f"{stdout_exp}\n"
                    "─────── Ficheros ───────\n" +
                    "\n".join(f"{k} → {v}" for k, v in filesEnd_exp.items())
                )

                _mostrar_error_scroll("Resultado de la corrección", msg)
                return

            aciertos += 1

    messagebox.showinfo("Correcto", f"🎉 ¡Todos los tests ({aciertos}) superados correctamente!")


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
