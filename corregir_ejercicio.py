# -*- coding: utf-8 -*-
"""
corregir_ejercicio.py
----------------------
Versión unificada para FI-UMH/Thonny

- Descarga tests.json (solo la primera vez).
- Corrige ejercicios de tipo:
    * pXXX  -> programas completos (main).
    * fXXX  -> funciones.
- Usa SIEMPRE un entorno aislado:
    * tempfile.TemporaryDirectory
    * subprocess.run con timeout.
- Muestra:
    * messagebox.showerror para errores "globales".
    * Ventana con scroll (_mostrar_error_scroll) para el detalle
      del primer test fallado.
"""

import sys
import os
import re
import io
import json
import subprocess
import tempfile
import traceback
import urllib.request
import urllib.parse
import socket
import uuid
import threading
from collections import Counter

from thonny import get_workbench
from tkinter import messagebox, Toplevel, Text, Scrollbar, Frame
import tkinter.font as tkfont

# -------------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------------

TESTS_URL = "https://raw.githubusercontent.com/FI-UMH/Thonny/main/tests.json"
_TESTS_CACHE = None

# -------------------------------------------------------------------------
# UTILIDADES DE INTERFAZ
# -------------------------------------------------------------------------


from tkinter import Toplevel, Text, Scrollbar, Frame
import tkinter.font as tkfont

def _mostrar_error_scroll(titulo, mensaje):
    win = Toplevel()
    win.title(titulo)
    win.geometry("820x520")

    # Frame contenedor para texto + scroll vertical
    frame = Frame(win)
    frame.pack(fill="both", expand=True)

    txt = Text(frame, wrap="none", font=("Consolas", 10))
    txt.pack(side="left", fill="both", expand=True)

    # Scroll vertical
    sy = Scrollbar(frame, orient="vertical", command=txt.yview)
    sy.pack(side="right", fill="y")
    txt.configure(yscrollcommand=sy.set)

    # Scroll horizontal
    sx = Scrollbar(win, orient="horizontal", command=txt.xview)
    sx.pack(side="bottom", fill="x")
    txt.configure(xscrollcommand=sx.set)

    # Insertar mensaje
    txt.insert("1.0", mensaje)

    # Negrita en títulos
    base = tkfont.Font(font=txt["font"])
    bold = base.copy()
    bold.configure(weight="bold")
    txt.tag_configure("titulo", font=bold, foreground="salmon4")
    txt.tag_configure("subtitulo", font=bold, foreground="salmon3")

    for palabra in ("CONTEXTO INICIAL", "RESULTADO OBTENIDO", "RESULTADO CORRECTO",
                    "ERRORES DETECTADOS" ):
        start = "1.0"
        while True:
            pos = txt.search(palabra, start, stopindex="end")
            if not pos:
                break
            end = f"{pos}+{len(palabra)}c"
            txt.tag_add("titulo", pos, end)
            start = end
            
    for palabra in ("─Argumentos", "─Retorno función","─Teclado",
                    "─Pantalla", "─Ficheros","─"):
        start = "1.0"
        while True:
            pos = txt.search(palabra, start, stopindex="end")
            if not pos:
                break
            end = f"{pos}+{len(palabra)}c"
            txt.tag_add("subtitulo", pos, end)
            start = end

    # Habilitar scroll con la rueda del ratón
    def _on_mousewheel(event):
        # Windows / macOS
        txt.yview_scroll(-int(event.delta / 120), "units")

    def _on_mousewheel_linux_up(event):
        txt.yview_scroll(-1, "units")

    def _on_mousewheel_linux_down(event):
        txt.yview_scroll(1, "units")

    txt.bind("<MouseWheel>", _on_mousewheel)        # Windows / macOS
    txt.bind("<Button-4>", _on_mousewheel_linux_up)   # Linux
    txt.bind("<Button-5>", _on_mousewheel_linux_down) # Linux

    txt.config(state="disabled")



# ======================================================================
#                SUBIR EJERCICIOS SIN REQUESTS
# ======================================================================


def _send_post(url, data):
    try:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(url, data=encoded, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=10) as f:
            return f.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _subir_ejercicios(dni, ejercicio, fuente):
    """Envía el ejercicio a los dos scripts de Google Apps Script."""
    try:
        hostname = socket.gethostname()

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_local = s.getsockname()[0]
            s.close()
        except Exception:
            ip_local = None

        mac_raw = uuid.getnode()
        mac = ":".join(
            f"{(mac_raw >> shift) & 0xff:02x}" for shift in range(40, -1, -8)
        )

        url_fi = (
            "https://script.google.com/macros/s/"
            "AKfycby3wCtvhy2sqLmp9TAl5aEQ4zHTceMAxwA_4M2HCjFJQpvxWmstEoRa5NohH0Re2eQa/exec"
        )
        url_pomares = (
            "https://script.google.com/macros/s/"
            "AKfycbw1CMfaQcJuP1cLBmt5eHryrmb83Tb0oIrWu_XHfRQpYt8kWY_g6TpsQx92QwhB_SjyYg/exec"
        )

        data = {
            "key": "Thonny#fi",
            "ordenador": hostname,
            "ip": ip_local,
            "mac": mac,
            "dni": dni,
            "ejercicio": ejercicio,
            "fuente": fuente,
        }

        _send_post(url_fi, data)
        _send_post(url_pomares, data)

    except Exception:
        # No queremos romper la corrección por un fallo de red
        pass


# -------------------------------------------------------------------------
# TESTS
# -------------------------------------------------------------------------


def _descargar_tests():
    """Descarga y cachea tests.json."""
    global _TESTS_CACHE
    if _TESTS_CACHE is not None:
        return _TESTS_CACHE

    try:
        with urllib.request.urlopen(TESTS_URL, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            _TESTS_CACHE = json.loads(data)
            return _TESTS_CACHE
    except Exception as e:
        messagebox.showerror(
            "Error", f"No se pudo descargar tests.json desde GitHub:\n{e}"
        )
        return None


# -------------------------------------------------------------------------
# UTILIDADES DE EJECUCIÓN Y COMPARACIÓN
# -------------------------------------------------------------------------


def _extraer_dni_ejercicio(fuente: str):
    """Obtiene DNI y EJERCICIO de las dos líneas de cabecera."""
    dni_m = re.search(r"^\s*#\s*DNI\s*=\s*(.+)$", fuente, re.MULTILINE)
    ejercicio_m = re.search(r"^\s*#\s*EJERCICIO\s*=\s*(.+)$", fuente, re.MULTILINE)

    dni = dni_m.group(1).strip() if dni_m else None
    ejercicio = ejercicio_m.group(1).strip() if ejercicio_m else None
    return dni, ejercicio


def _preprocesar_fuente(src: str) -> str:
    """
    Sustituye input(...) por inputt(...), para que se vean en pantalla
    las entradas por teclado del alumno durante la corrección.
    """
    src_mod = re.sub(r"input\s*\(", "inputt(", src)
    cabecera = (
        "def inputt(msg=''):\n"
        "    x = input(msg)\n"
        "    print(x)\n"
        "    return x\n\n"
    )
    return cabecera + src_mod


def _decode_bytes(b: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    return b.decode("utf-8", errors="replace")


def _comparar_resultados_pantalla(pantalla_obt: str, pantalla_exp: str):
    """
    Compara únicamente los resultados entre paréntesis, ignorando espacios
    y sin tener en cuenta el orden. Devuelve (ok: bool, lista_errores: list[str]).
    """
    patron = r"\((.*?)\)"

    diferencias = []

    obt_abre = pantalla_obt.count("(")
    obt_cierra = pantalla_obt.count(")")
    exp_abre = pantalla_exp.count("(")
    exp_cierra = pantalla_exp.count(")")

    # Paréntesis desbalanceados
    if obt_abre != obt_cierra:
        diferencias.append(
            f"Paréntesis desbalanceados en la salida obtenida: "
            f"{obt_abre} '(' vs {obt_cierra} ')'."
        )
        return False, diferencias

    if exp_abre != exp_cierra:
        diferencias.append(
            f"Paréntesis desbalanceados en la salida correcta: "
            f"{exp_abre} '(' vs {exp_cierra} ')'."
        )
        return False, diferencias

    # Conteo de resultados
    if obt_abre != exp_abre:
        diferencias.append(
            f"Número de resultados distinto. Obtenida: {obt_abre}, Correcta: {exp_abre}."
        )

    # Extraer resultados y eliminar espacios internos
    res_obt = [r.replace(" ", "") for r in re.findall(patron, pantalla_obt)]
    res_exp = [r.replace(" ", "") for r in re.findall(patron, pantalla_exp)]

    # Comparar ignorando orden (multiconjuntos)
    cnt_obt = Counter(res_obt)
    cnt_exp = Counter(res_exp)

    if cnt_obt != cnt_exp:
        # Resultados que faltan o sobran
        faltan = []
        for val, n in cnt_exp.items():
            if cnt_obt[val] < n:
                faltan.append(val)
        if faltan:
            diferencias.append(f"Faltan resultados: {faltan}")
        diferencias.append(f"Obtenidos: {res_obt}")
        diferencias.append(f"Correctos: {res_exp}")
        return False, diferencias

    return True, []


def _comparar_ficheros(ficheros_obt: dict, ficheros_exp: dict):
    """
    Compara nombres y contenido de ficheros.
    Devuelve (ok: bool, lista_errores: list[str]).
    """
    diferencias = []

    nombres_obt = set(ficheros_obt.keys())
    nombres_exp = set(ficheros_exp.keys())

    faltan = nombres_exp - nombres_obt
    sobran = nombres_obt - nombres_exp

    if faltan:
        diferencias.append(f"Faltan ficheros: {sorted(list(faltan))}")
    if sobran:
        diferencias.append(f"Ficheros inesperados: {sorted(list(sobran))}")

    if diferencias:
        return False, diferencias

    # Contenido
    for nombre in nombres_exp:
        if ficheros_obt[nombre] != ficheros_exp[nombre]:
            diferencias.append(
                f"El contenido del fichero '{nombre}' es diferente."
            )

    if diferencias:
        return False, diferencias

    return True, []


def _formatear_dict_ficheros(d: dict) -> str:
    if not d:
        return "(sin ficheros)"
    # Ordenamos por nombre para que sea más legible
    lineas = [f"{nombre} → {contenido}" for nombre, contenido in sorted(d.items())]
    return "\n".join(lineas)


# -------------------------------------------------------------------------
# EJECUCIÓN AISLADA EN SUBPROCESO
# -------------------------------------------------------------------------


def _run_test_programa(fuente: str, test: dict) -> dict:
    """
    Ejecuta un programa del alumno en un entorno aislado.
    Devuelve:
        {
            "stdout": str,
            "files_end": dict,
            "error_tipo": None | "tiempo" | "ejecucion" | "interno",
            "error_detalle": str
        }
    """
    res = {
        "stdout": "",
        "files_end": {},
        "error_tipo": None,
        "error_detalle": "",
    }

    stdin_content = test.get("stdin", "")
    files_ini = test.get("filesIni") or {}

    try:
        with tempfile.TemporaryDirectory(prefix="corr_") as td:
            # Escribir fuente del alumno
            alumno_py = os.path.join(td, "alumno.py")
            src_mod = _preprocesar_fuente(fuente)
            with open(alumno_py, "w", encoding="utf-8") as f:
                f.write(src_mod)

            # Ficheros iniciales
            for fn, content in files_ini.items():
                fn_path = os.path.join(td, fn)
                os.makedirs(os.path.dirname(fn_path) or td, exist_ok=True)
                with open(fn_path, "w", encoding="utf-8") as f:
                    f.write(content)

            # Ejecutar
            completed = subprocess.run(
                [sys.executable, alumno_py],
                cwd=td,
                input=stdin_content.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )

            stdout = _decode_bytes(completed.stdout)
            stderr = _decode_bytes(completed.stderr)

            res["stdout"] = stdout

            # Ficheros finales (solo nivel raíz, excepto alumno.py)
            files_now = {}
            for name in os.listdir(td):
                p = os.path.join(td, name)
                if os.path.isdir(p):
                    continue
                if name == "alumno.py":
                    continue
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    files_now[name] = f.read()

            res["files_end"] = files_now

            if completed.returncode != 0:
                res["error_tipo"] = "ejecucion"
                res["error_detalle"] = (
                    stderr
                    or f"El intérprete terminó con código de salida {completed.returncode}."
                )

    except subprocess.TimeoutExpired:
        res["error_tipo"] = "tiempo"
        res["error_detalle"] = "Tiempo excedido (posible bucle infinito)."
    except Exception as e:
        res["error_tipo"] = "interno"
        res["error_detalle"] = (
            f"Error interno al ejecutar el test:\n{e}\n{traceback.format_exc()}"
        )

    return res


def _run_test_funcion(fuente: str, test: dict) -> dict:
    """
    Ejecuta una FUNCIÓN del alumno en un entorno aislado.

    Devuelve:
        {
            "stdout": str,
            "files_end": dict,
            "ret": Any,
            "error_tipo": None | "tiempo" | "ejecucion" | "interno",
            "error_detalle": str
        }
    """
    res = {
        "stdout": "",
        "files_end": {},
        "ret": None,
        "error_tipo": None,
        "error_detalle": "",
    }

    nombre_funcion = test.get("funcName")
    args = test.get("args", [])
    stdin_content = test.get("stdin", "")
    files_ini = test.get("filesIni") or {}

    if not nombre_funcion:
        res["error_tipo"] = "interno"
        res["error_detalle"] = "El test no define 'funcName'."
        return res

    try:
        with tempfile.TemporaryDirectory(prefix="corr_") as td:
            # Escribir fuente del alumno
            alumno_py = os.path.join(td, "alumno.py")
            src_mod = _preprocesar_fuente(fuente)
            with open(alumno_py, "w", encoding="utf-8") as f:
                f.write(src_mod)

            # Ficheros iniciales
            for fn, content in files_ini.items():
                fn_path = os.path.join(td, fn)
                os.makedirs(os.path.dirname(fn_path) or td, exist_ok=True)
                with open(fn_path, "w", encoding="utf-8") as f:
                    f.write(content)

            # Script envoltorio que importa alumno y llama a la función
            args_json = json.dumps(args, ensure_ascii=False)
            wrapper_code = (
                "import json, alumno, sys\n"
                "args = json.loads(sys.argv[1])\n"
                f"ret = getattr(alumno, {nombre_funcion!r})(*args)\n"
                "print('__RET__=' + json.dumps(ret, ensure_ascii=False))\n"
            )

            completed = subprocess.run(
                [sys.executable, "-c", wrapper_code, args_json],
                cwd=td,
                input=stdin_content.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )

            stdout_total = _decode_bytes(completed.stdout)
            stderr = _decode_bytes(completed.stderr)

            # Ficheros finales (solo nivel raíz, excepto alumno.py)
            files_now = {}
            for name in os.listdir(td):
                p = os.path.join(td, name)
                if os.path.isdir(p):
                    continue
                if name == "alumno.py":
                    continue
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    files_now[name] = f.read()

            res["files_end"] = files_now

            if completed.returncode != 0:
                res["error_tipo"] = "ejecucion"
                res["error_detalle"] = (
                    stderr
                    or f"El intérprete terminó con código de salida {completed.returncode}."
                )
                res["stdout"] = stdout_total
                return res

            # Extraer la línea __RET__=... del stdout y decodificar el JSON
            sentinel = "__RET__="
            lineas = stdout_total.splitlines(keepends=True)
            idx_sentinel = None
            for i in range(len(lineas) - 1, -1, -1):
                if lineas[i].startswith(sentinel):
                    idx_sentinel = i
                    break

            if idx_sentinel is None:
                res["error_tipo"] = "ejecucion"
                res["error_detalle"] = (
                    "No se pudo obtener el valor devuelto de la función "
                    "(no se encontró la marca __RET__ en la salida)."
                )
                res["stdout"] = stdout_total
                return res

            linea_ret = lineas.pop(idx_sentinel)
            ret_json = linea_ret[len(sentinel) :].strip()

            try:
                ret_val = json.loads(ret_json)
            except Exception as e:
                res["error_tipo"] = "ejecucion"
                res["error_detalle"] = (
                    f"No se pudo decodificar el valor retornado de la función:\n{e}"
                )
                res["stdout"] = "".join(lineas)
                return res

            res["ret"] = ret_val
            res["stdout"] = "".join(lineas)

    except subprocess.TimeoutExpired:
        res["error_tipo"] = "tiempo"
        res["error_detalle"] = "Tiempo excedido (posible bucle infinito)."
    except Exception as e:
        res["error_tipo"] = "interno"
        res["error_detalle"] = (
            f"Error interno al ejecutar el test de función:\n{e}\n{traceback.format_exc()}"
        )

    return res


# -------------------------------------------------------------------------
# FORMATEO DE MENSAJES DE ERROR
# -------------------------------------------------------------------------


def _mensaje_error_programa(errores, test, stdout_obt, files_end_text):
    files_ini = test.get("filesIni") or {}
    stdout_ok = test.get("stdout_ok", "")
    files_end_ok = test.get("filesEnd_ok") or {}

    partes = []
    partes.append("El ejercicio no supera el test")
    partes.append("")

    if errores:
        partes.append("   ERRORES DETECTADOS:")
        for err in errores:
            partes.append(f"- {err}")
        partes.append("")

    partes.append("    CONTEXTO INICIAL")
    partes.append("────────Teclado──────────")
    partes.append(test.get("stdin", ""))
    partes.append("────────Ficheros─────────")
    partes.append(_formatear_dict_ficheros(files_ini))
    partes.append("")

    partes.append("   RESULTADO OBTENIDO")
    partes.append("────────Pantalla─────────")
    partes.append(stdout_obt)
    partes.append("────────Ficheros─────────")
    partes.append(files_end_text)
    partes.append("")

    partes.append("   RESULTADO CORRECTO")
    partes.append("────────Pantalla─────────")
    partes.append(stdout_ok)
    partes.append("────────Ficheros─────────")
    partes.append(_formatear_dict_ficheros(files_end_ok))

    return "\n".join(partes)


def _mensaje_error_funcion(errores, test, stdout_obt, files_end_text, ret_obt):
    files_ini = test.get("filesIni") or {}
    stdout_ok = test.get("stdout_ok", "")
    files_end_ok = test.get("filesEnd_ok") or {}
    ret_ok = test.get("return_ok")

    partes = []
    partes.append("El ejercicio no supera el test")
    partes.append("")

    if errores:
        partes.append("   ERRORES DETECTADOS:")
        for err in errores:
            partes.append(f"- {err}")
        partes.append("")

    partes.append("    CONTEXTO INICIAL")
    partes.append("───────Argumentos────────")
    partes.append(repr(test.get("args", [])))
    partes.append("────────Teclado──────────")
    partes.append(test.get("stdin", ""))
    partes.append("────────Ficheros─────────")
    partes.append(_formatear_dict_ficheros(files_ini))
    partes.append("")

    partes.append("   RESULTADO OBTENIDO")
    partes.append("─────Retorno función─────")
    partes.append(repr(ret_obt))
    partes.append("────────Pantalla─────────")
    partes.append(stdout_obt)
    partes.append("────────Ficheros─────────")
    partes.append(files_end_text)
    partes.append("")

    partes.append("   RESULTADO CORRECTO")
    partes.append("─────Retorno función─────")
    partes.append(repr(ret_ok))
    partes.append("────────Pantalla─────────")
    partes.append(stdout_ok)
    partes.append("────────Ficheros─────────")
    partes.append(_formatear_dict_ficheros(files_end_ok))

    return "\n".join(partes)


# -------------------------------------------------------------------------
# FUNCIÓN DE CORRECCIÓN UNIFICADA
# -------------------------------------------------------------------------


def corregir_ejercicio(dni, ejercicio, fuente, lista_tests):
    """
    Corrige tanto programas (pXXX) como funciones (fXXX) usando un único
    flujo de trabajo. El tipo se decide por el prefijo del ejercicio.
    """
    if not lista_tests:
        messagebox.showerror(
            "Error",
            f"No hay tests definidos para el ejercicio {ejercicio}.",
        )
        return

    if ejercicio is None:
        messagebox.showerror(
            "Error",
            "No se ha encontrado el identificador de ejercicio en la cabecera.",
        )
        return

    ej_lower = ejercicio.lower()
    if ej_lower.startswith("p"):
        tipo = "programa"
    elif ej_lower.startswith("f"):
        tipo = "funcion"
    else:
        messagebox.showerror(
            "Error",
            "El identificador de ejercicio debe empezar por 'p' o por 'f'.",
        )
        return

    total = len(lista_tests)

    for idx, test in enumerate(lista_tests, start=1):
        errores = []

        if tipo == "programa":
            # -----------------------------------------------------
            # 1) Ejecutar programa en entorno aislado
            # -----------------------------------------------------
            res = _run_test_programa(fuente, test)
            stdout_obt = res.get("stdout", "")
            files_end = res.get("files_end", {})

            # -----------------------------------------------------
            # 2) Chequeos en el orden solicitado:
            #    tiempo -> ejecución -> ficheros -> pantalla
            # -----------------------------------------------------
            if res["error_tipo"] == "tiempo":
                errores.append(res["error_detalle"])
            elif res["error_tipo"] == "ejecucion":
                errores.append("Error de ejecución del programa.")
                if res["error_detalle"]:
                    errores.append(res["error_detalle"])
            elif res["error_tipo"] == "interno":
                errores.append("Error interno en el sistema de corrección.")
                if res["error_detalle"]:
                    errores.append(res["error_detalle"])
            else:
                # Comparación de ficheros
                exp_files = test.get("filesEnd_ok") or {}
                ok_files, dif_files = _comparar_ficheros(files_end, exp_files)
                if not ok_files:
                    errores.append("Error al comparar ficheros finales.")
                    errores.extend(dif_files)
                else:
                    # Comparación de salida por pantalla
                    exp_stdout = test.get("stdout_ok", "")
                    ok_out, dif_out = _comparar_resultados_pantalla(
                        stdout_obt, exp_stdout
                    )
                    if not ok_out:
                        errores.append("Error al comparar la salida por pantalla.")
                        errores.extend(dif_out)

            if errores:
                files_end_text = _formatear_dict_ficheros(files_end)
                msg = _mensaje_error_programa(
                    errores, test, stdout_obt, files_end_text
                )
                _mostrar_error_scroll("Error en el test", msg)
                '''
                messagebox.showerror(
                    "Resultado de la corrección",
                    f"El ejercicio no supera el test {idx} de {total}.",
                )
                '''
                return

        else:  # tipo == "funcion"
            # -----------------------------------------------------
            # 1) Ejecutar función en entorno aislado
            # -----------------------------------------------------
            res = _run_test_funcion(fuente, test)
            stdout_obt = res.get("stdout", "")
            files_end = res.get("files_end", {})
            ret_obt = res.get("ret", None)

            # -----------------------------------------------------
            # 2) Chequeos en el orden solicitado:
            #    tiempo -> ejecución -> retorno -> pantalla -> ficheros
            # -----------------------------------------------------
            if res["error_tipo"] == "tiempo":
                errores.append(res["error_detalle"])
            elif res["error_tipo"] == "ejecucion":
                errores.append("Error de ejecución de la función.")
                if res["error_detalle"]:
                    errores.append(res["error_detalle"])
            elif res["error_tipo"] == "interno":
                errores.append("Error interno en el sistema de corrección.")
                if res["error_detalle"]:
                    errores.append(res["error_detalle"])
            else:
                # Retorno
                exp_ret = test.get("return_ok")
                if ret_obt != exp_ret:
                    errores.append(
                        "Error al comparar el retorno de la función."
                    )
                    errores.append(f"Obtenido: {ret_obt!r}")
                    errores.append(f"Correcto: {exp_ret!r}")
                else:
                    # Pantalla
                    exp_stdout = test.get("stdout_ok", "")
                    ok_out, dif_out = _comparar_resultados_pantalla(
                        stdout_obt, exp_stdout
                    )
                    if not ok_out:
                        errores.append(
                            "Error al comparar la salida por pantalla."
                        )
                        errores.extend(dif_out)
                    else:
                        # Ficheros
                        exp_files = test.get("filesEnd_ok") or {}
                        ok_files, dif_files = _comparar_ficheros(
                            files_end, exp_files
                        )
                        if not ok_files:
                            errores.append(
                                "Error al comparar los ficheros finales."
                            )
                            errores.extend(dif_files)

            if errores:
                files_end_text = _formatear_dict_ficheros(files_end)
                msg = _mensaje_error_funcion(
                    errores, test, stdout_obt, files_end_text, ret_obt
                )
                _mostrar_error_scroll("Error en el test", msg)
                '''
                messagebox.showerror(
                    "Resultado de la corrección",
                    f"El ejercicio no supera el test {idx} de {total}.",
                )
                '''
                return

    # -----------------------------------------------------------------
    # Si hemos llegado aquí, todos los tests han sido superados
    # -----------------------------------------------------------------
    threading.Thread(
        target=_subir_ejercicios,
        args=(dni, ejercicio, fuente),
        daemon=True,
    ).start()
    messagebox.showinfo(
        "Resultado de la corrección",
        "El ejercicio supera todos los tests.",
    )


# -------------------------------------------------------------------------
# WRAPPERS (compatibilidad con el esquema original)
# -------------------------------------------------------------------------


def _corregir_ejercicio_programa(dni, ejercicio, fuente, lista_tests):
    return corregir_ejercicio(dni, ejercicio, fuente, lista_tests)


def _corregir_ejercicio_funcion(dni, ejercicio, fuente, lista_tests):
    return corregir_ejercicio(dni, ejercicio, fuente, lista_tests)


# -------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL (llamada desde configuracion.py)
# -------------------------------------------------------------------------


def main():
    wb = get_workbench()
    ed = wb.get_editor_notebook().get_current_editor()

    if not ed:
        messagebox.showerror("Error", "No hay ningún editor activo.")
        return

    try:
        fuente = ed.get_text_widget().get("1.0", "end-1c")
    except Exception:
        # Fallback por si cambia la API de Thonny
        try:
            fuente = ed.get_content()
        except Exception:
            fuente = ""

    if not fuente.strip():
        messagebox.showerror(
            "Error", "El archivo actual está vacío o no se ha podido leer."
        )
        return

    dni, ejercicio = _extraer_dni_ejercicio(fuente)

    if not dni:
        messagebox.showerror(
            "Error",
            "No se encontró '# DNI =' en la cabecera del archivo.",
        )
        return

    if not ejercicio:
        messagebox.showerror(
            "Error",
            "No se encontró '# EJERCICIO =' en la cabecera del archivo.",
        )
        return

    tests = _descargar_tests()
    if is None:
        # _descargar_tests ya muestra el error
        return

    if ejercicio not in tests:
        messagebox.showerror(
            "Error",
            f"No existen tests para el ejercicio '{ejercicio}'.",
        )
        return

    lista_tests = tests[ejercicio]
    print(tests[ejercicio])  #########################################################################
    corregir_ejercicio(dni, ejercicio, fuente, lista_tests)
