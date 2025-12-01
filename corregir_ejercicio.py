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
import re
import json
import urllib.request
import io
from thonny import get_workbench
from tkinter import messagebox, Toplevel, Text, Scrollbar
import tkinter.font as tkfont
import urllib.parse
import socket
import uuid

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

# ======================================================================
#                SUBIR EJERCICIO SIN REQUESTS
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
        mac = ":".join(f"{(mac_raw >> shift) & 0xff:02x}"
                       for shift in range(40, -1, -8))

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
        pass


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


def _extraer_dni_ejercicio(fuente):
    dni_m = re.search(r"^\s*#\s*DNI\s*=\s*(.+)$", fuente, re.MULTILINE)
    ejercicio_m  = re.search(r"^\s*#\s*EJERCICIO\s*=\s*(.+)$", fuente, re.MULTILINE)
    dni = dni_m.group(1).strip() if dni_m else None
    ejercicio  = ejercicio_m.group(1).strip() if ejercicio_m else None
    return dni, ejercicio


def _preprocesar_fuente(src: str) -> str:
    src_mod = re.sub(r"input\s*\(", "inputt(", src)
    cabecera = (
        "def inputt(msg=''):\n"
        "    x = input(msg)\n"
        "    print(x)\n"
        "    return x\n\n"
    )
    return cabecera + src_mod

def _ejecutar_programa(fuente: str, test: dict):
    # Capturar stdin
    stdin_val = test.get("stdin", "")
    stdin_backup = sys.stdin
    sys.stdin = io.StringIO(stdin_val)

    # Capturar stdout
    stdout_backup = sys.stdout
    stdout_cap = io.StringIO()
    sys.stdout = stdout_cap

    # Sistema de ficheros inicial
    files_ini = test.get("files", {}).copy()
    files_end = files_ini.copy()

    # Entorno aislado
    entorno = {
        "__name__": "__main__",
        "FILES": files_end
    }

    try:
        exec(_preprocesar_fuente(fuente), entorno)
    except Exception as e:
        sys.stdin = stdin_backup
        sys.stdout = stdout_backup
        return {"stdout": f"ERROR: {e}"}, files_ini, files_end

    # Restaurar I/O
    sys.stdin = stdin_backup
    sys.stdout = stdout_backup

    salida = {"stdout": stdout_cap.getvalue()}
    return salida, files_ini, files_end


def _ejecutar_funcion(fuente: str, nombre_funcion: str, args: list):
    entorno = {"__name__": "__main__", "FILES": {}}

    # Ejecutar código del alumno
    try:
        exec(_preprocesar_fuente(fuente), entorno)
    except Exception as e:
        return {"stdout": "", "return": f"ERROR: {e}", "files": {}}

    # Verificar función
    if nombre_funcion not in entorno or not callable(entorno[nombre_funcion]):
        return {"stdout": "", "return": f"ERROR: función '{nombre_funcion}' no definida", "files": {}}

    funcion = entorno[nombre_funcion]

    # Capturar stdout
    stdout_backup = sys.stdout
    stdout_cap = io.StringIO()
    sys.stdout = stdout_cap

    try:
        ret = funcion(*args)
    except Exception as e:
        sys.stdout = stdout_backup
        return {"stdout": "", "return": f"ERROR: {e}", "files": entorno.get("FILES", {})}

    # Restaurar stdout
    sys.stdout = stdout_backup

    return {
        "stdout": stdout_cap.getvalue(),
        "return": ret,
        "files": entorno.get("FILES", {})
    }



def _comparar_resultados_pantalla(pantalla_obt: str, pantalla_exp: str):
    patron = r"\((.*?)\)"

    diferencias = []

    obt_abre = pantalla_obt.count("(")
    obt_cierra = pantalla_obt.count(")")
    exp_abre = pantalla_exp.count("(")
    exp_cierra = pantalla_exp.count(")")

    # Paréntesis desbalanceados
    if obt_abre != obt_cierra:
        diferencias.append(f"Paréntesis desbalanceados en la salida obtenida: {obt_abre} '(' vs {obt_cierra} ')'.")
        return False, diferencias

    if exp_abre != exp_cierra:
        diferencias.append(f"Paréntesis desbalanceados en la salida correcta: {exp_abre} '(' vs {exp_cierra} ')'.")
        return False, diferencias

    # Conteo de resultados
    if obt_abre != exp_abre:
        diferencias.append(f"Número de resultados distinto. Obtenida: {obt_abre}, Correcta: {exp_abre}.")

    # Extraer resultados
    res_obt = [r.replace(" ", "") for r in re.findall(patron, pantalla_obt)]
    res_exp = [r.replace(" ", "") for r in re.findall(patron, pantalla_exp)]

    # Comparar sin orden
    faltan = [r for r in res_exp if r not in res_obt]

    if faltan:
        diferencias.append(f"Faltan resultados: {faltan}")
        diferencias.append(f"Obtenidos: {res_obt}")
        diferencias.append(f"Correctos: {res_exp}")
        return False, diferencias

    return True, []


def _comparar_ficheros(ficheros_obt: dict, ficheros_exp: dict):
    diferencias = []

    # Nombres
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
            diferencias.append(f"El contenido del fichero '{nombre}' es diferente.")

    if diferencias:
        return False, diferencias

    return True, []


# -------------------------------------------------------------------------
# CORRECCIÓN DE PROGRAMAS pXXX
# -------------------------------------------------------------------------

def _corregir_ejercicio_programa(dni, ejercicio, fuente, lista_tests):

    for idx, test in enumerate(lista_tests, start=1):

        # ---------------------------------------------------------
        # 1. Ejecutar programa
        # ---------------------------------------------------------
        salida, files_ini, files_end = _ejecutar_programa(fuente, test)

        stdout_obt = salida.get("stdout", "")
        stdout_exp = test.get("stdout", "")

        # Textos ficheros
        filesIni_text = "\n".join(f"{k} → {v}" for k, v in files_ini.items()) or "(sin ficheros)"
        files_end_text = "\n".join(f"{k} → {v}" for k, v in files_end.items()) or "(sin ficheros)"
        filesEnd_exp_text = "\n".join(f"{k} → {v}" for k, v in test.get("files", {}).items()) or "(sin ficheros)"

        # ---------------------------------------------------------
        # 2. Comparación pantalla
        # ---------------------------------------------------------
        ok_pantalla, dif_pantalla = _comparar_resultados_pantalla(stdout_obt, stdout_exp)

        # ---------------------------------------------------------
        # 3. Comparación ficheros
        # ---------------------------------------------------------
        ok_files, dif_files = _comparar_ficheros(files_end, test.get("files", {}))

        # ---------------------------------------------------------
        # 4. Si todo bien -> siguiente test
        # ---------------------------------------------------------
        if ok_pantalla and ok_files:
            continue

        # ---------------------------------------------------------
        # 5. DIFERENCIAS DETECTADAS
        # ---------------------------------------------------------
        diferencias_detectadas = "\n".join(dif_pantalla + dif_files)

        # ---------------------------------------------------------
        # 6. MENSAJE FINAL UNIFICADO
        # ---------------------------------------------------------
        msg = (
            "El ejercicio no supera el test.\n\n"
            "DIFERENCIAS DETECTADAS:\n"
            + diferencias_detectadas
            + "\n\n"
            "▶ CONTEXTO INICIAL\n"
            "─────── Teclado ───────\n"
            f"{test.get('stdin', '')}\n"
            "─────── Ficheros ───────\n"
            + filesIni_text
            + "\n\n"
            "▶ RESULTADO OBTENIDO\n"
            "─────── Pantalla ───────\n"
            f"{stdout_obt}\n"
            "─────── Ficheros ───────\n"
            + files_end_text
            + "\n\n"
            "▶ RESULTADO CORRECTO\n"
            "─────── Pantalla ───────\n"
            f"{stdout_exp}\n"
            "─────── Ficheros ───────\n"
            + filesEnd_exp_text
        )

        _mostrar_error_scroll("Resultado de la corrección", msg)
        return
    
    # ---------------------------------------------------------
    # CORRECTO - ENVIO EJERCICIO A SERVIDORES 
    # ---------------------------------------------------------
    threading.Thread(
        target=_subir_ejercicios,
        args=(dni, ejercicio, fuente),
        daemon=True
    ).start()
    messagebox.showinfo("Resultado de la corrección", "El ejercicio supera todos los tests.")
    return

# -------------------------------------------------------------------------
# CORRECCIÓN DE FUNCIONES fXXX
# -------------------------------------------------------------------------

def _corregir_ejercicio_funcion(dni, ejercicio, fuente, lista_tests):

    for idx, test in enumerate(lista_tests, start=1):

        nombre_funcion = test["funcName"]
        args = test.get("args", [])
        stdin_val = test.get("stdin", "")

        # ---------------------------------------------------------
        # 1. Ejecutar función del alumno
        # ---------------------------------------------------------
        try:
            salida = _ejecutar_funcion(
                codigo,
                nombre_funcion,
                args
            )
        except Exception as e:
            msg = (
                "La función NO supera el test.\n\n"
                f"Error al ejecutar la función: {e}\n\n"
                f"FUNCION: {nombre_funcion}\n"
                f"ARGUMENTOS: {args}\n"
            )
            _mostrar_error_scroll("Resultado de la corrección", msg)
            return

        stdout_obt = salida.get("stdout", "")
        ret_obt = salida.get("return", None)
        files_end = salida.get("files", {})

        stdout_exp = test.get("stdout", "")
        ret_exp = test.get("return", None)
        files_end_exp = test.get("files", {})

        # Textos de ficheros (aunque casi nunca se usan en funciones)
        filesIni_text = "(sin ficheros)"
        files_end_text = "\n".join(f"{k} → {v}" for k, v in files_end.items()) or "(sin ficheros)"
        filesEnd_exp_text = "\n".join(f"{k} → {v}" for k, v in files_end_exp.items()) or "(sin ficheros)"

        # ---------------------------------------------------------
        # 2. Comparación pantalla
        # ---------------------------------------------------------
        ok_pantalla, dif_pantalla = _comparar_resultados_pantalla(stdout_obt, stdout_exp)

        # ---------------------------------------------------------
        # 3. Comparación return
        # ---------------------------------------------------------
        ok_return = (ret_obt == ret_exp)
        dif_return = []

        if not ok_return:
            dif_return.append(f"Valor retornado incorrecto. Obtenido: {ret_obt}, Correcto: {ret_exp}")

        # ---------------------------------------------------------
        # 4. Comparación ficheros
        # ---------------------------------------------------------
        ok_files, dif_files = _comparar_ficheros(files_end, files_end_exp)

        # ---------------------------------------------------------
        # 5. ¿Todo OK?
        # ---------------------------------------------------------
        if ok_pantalla and ok_return and ok_files:
            continue

        # ---------------------------------------------------------
        # 6. DIFERENCIAS DETECTADAS
        # ---------------------------------------------------------
        diferencias_detectadas = "\n".join(dif_pantalla + dif_return + dif_files)

        # ---------------------------------------------------------
        # 7. MENSAJE FINAL UNIFICADO
        # ---------------------------------------------------------
        msg = (
            "La función NO supera el test.\n\n"
            "DIFERENCIAS DETECTADAS:\n"
            + diferencias_detectadas
            + "\n\n"
            f"FUNCION: {nombre_funcion}\n"
            f"ARGUMENTOS: {args}\n\n"
            "▶ CONTEXTO INICIAL\n"
            "─────── Teclado ───────\n"
            f"{stdin_val}\n"
            "─────── Ficheros ───────\n"
            + filesIni_text
            + "\n\n"
            "▶ RESULTADO OBTENIDO\n"
            "─────── return ───────\n"
            f"{ret_obt!r}\n"
            "─────── Pantalla ───────\n"
            f"{stdout_obt}\n"
            "─────── Ficheros ───────\n"
            + files_end_text
            + "\n\n"
            "▶ RESULTADO CORRECTO\n"
            "─────── return ───────\n"
            f"{ret_exp!r}\n"
            "─────── Pantalla ───────\n"
            f"{stdout_exp}\n"
            "─────── Ficheros ───────\n"
            + filesEnd_exp_text
        )

        _mostrar_error_scroll("Resultado de la corrección", msg)
        return

    # ---------------------------------------------------------
    # CORRECTO - ENVIO EJERCICIO A SERVIDORES 
    # ---------------------------------------------------------
    threading.Thread(
        target=_subir_ejercicios,
        args=(dni, ejercicio, fuente),
        daemon=True
    ).start()
    messagebox.showinfo("Resultado de la corrección", "El ejercicio supera todos los tests.")
    return

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
        fuente = ed.get_text_widget().get("1.0", "end-1c")
    except:
        fuente = ""

    dni, ejercicio = _extraer_dni_ejercicio(fuente)

    if not ejercicio:
        messagebox.showerror("Error", "No se encontró '# EJERCICIO =' en la cabecera.")
        return

    tests = _descargar_tests()
    if not tests or ejercicio not in tests:
        messagebox.showerror("Error", f"No existen tests para el ejercicio {ejercicio}.")
        return

    lista = tests[ejercicio]

    if ejercicio.startswith("p"):
        _corregir_ejercicio_programa(dni, ejercicio, fuente, lista)
    elif ejercicio.startswith("f"):
        _corregir_ejercicio_funcion(dni, ejercicio, fuente, lista)
    else:
        messagebox.showerror("Error", "El identificativo de ejercicio debe empezar por 'p' o 'f'.")
