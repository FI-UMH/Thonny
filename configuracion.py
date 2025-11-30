# -*- coding: utf-8 -*-
"""
Nuevo configuracion.py (versión modular final)
----------------------------------------------
- Mantiene TODA la configuración del Thonny original:
    ✔ Inserción de cabecera (DNI + EJERCICIO)
    ✔ Vista de Variables y Shell activadas
    ✔ Mensajes de guardar antes de ejecutar
- Añade carga dinámica modular de:
    - descargar_ficheros.py
    - corregir_ejercicio.py
"""

import sys
import urllib.request
import importlib.util
from thonny import get_workbench
from tkinter import messagebox


# -------------------------------------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------------------------------------

BASE_URL = "https://raw.githubusercontent.com/FI-UMH/Thonny/main/"

# Se usará para rellenar la cabecera
ALUMNO_DNI = ""


# -------------------------------------------------------------------------
# CARGADOR DINÁMICO DE MÓDULOS
# -------------------------------------------------------------------------

def cargar_o_importar(nombre_modulo):
    """
    Carga el módulo desde FI-UMH/Thonny si no existe en sys.modules.
    Lo ejecuta en memoria y lo deja disponible de forma persistente.
    """
    if nombre_modulo in sys.modules:
        return sys.modules[nombre_modulo]

    url = BASE_URL + nombre_modulo + ".py"

    try:
        with urllib.request.urlopen(url) as resp:
            codigo = resp.read().decode("utf-8")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo descargar {nombre_modulo}.py:\n{e}")
        return None

    spec = importlib.util.spec_from_loader(nombre_modulo, loader=None)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre_modulo] = mod

    try:
        exec(codigo, mod.__dict__)
    except Exception as e:
        messagebox.showerror("Error", f"Error ejecutando {nombre_modulo}.py:\n{e}")
        return None

    return mod


# -------------------------------------------------------------------------
# CABECERA EN LOS ARCHIVOS NUEVOS
# -------------------------------------------------------------------------

def _config_cabecera():
    """
    Restaura la lógica original de insertar automáticamente:
        # DNI = XXXXX
        # EJERCICIO =
    en cada archivo nuevo.
    """

    from thonny.editors import Editor

    # Guardamos el __init__ original
    _old_init = Editor.__init__

    def _hook(self, *args, **kwargs):
        _old_init(self, *args, **kwargs)

        if self.get_filename() is None:  # archivo nuevo
            global ALUMNO_DNI
            cabecera = f"# DNI = {ALUMNO_DNI}\n# EJERCICIO = \n\n"
            try:
                widget = self.get_text_widget()
                widget.insert("1.0", cabecera)
            except Exception:
                self.set_text(cabecera)

    Editor.__init__ = _hook

    # Insertar la cabecera en la primera pestaña ya abierta
    def inicial():
        wb = get_workbench()
        ed = wb.get_editor_notebook().get_current_editor()
        if ed and ed.get_filename() is None:
            global ALUMNO_DNI
            cabecera = f"# DNI = {ALUMNO_DNI}\n# EJERCICIO = \n\n"
            try:
                w = ed.get_text_widget()
                w.delete("1.0", "end")
                w.insert("1.0", cabecera)
            except Exception:
                ed.set_text(cabecera)

    wb = get_workbench()
    wb.after(500, inicial)


# -------------------------------------------------------------------------
# ACTIVAR VISTAS
# -------------------------------------------------------------------------

def _config_vistas():
    wb = get_workbench()

    def activar():
        try:
            wb.show_view("VariablesView", True)
            wb.show_view("ShellView", True)
        except Exception:
            pass

    wb.after(800, activar)


# -------------------------------------------------------------------------
# OBLIGAR A GUARDAR ANTES DE EJECUTAR
# -------------------------------------------------------------------------

def _config_guardar_antes():
    wb = get_workbench()

    def necesita_guardar():
        ed = wb.get_editor_notebook().get_current_editor()
        if ed is None:
            return False

        if ed.get_filename() is None:
            messagebox.showinfo("Guardar archivo",
                                "Debes guardar el archivo antes de ejecutar.")
            wb.get_menu("file").invoke_command("save_as")
            return True

        if ed.is_modified():
            messagebox.showinfo("Guardar archivo",
                                "Guarda el archivo antes de ejecutar.")
            wb.get_menu("file").invoke_command("save")
            return True

        return False

    def intercept(event=None):
        if necesita_guardar():
            return "break"

    wb.bind("<<RunScript>>", intercept, True)
    wb.bind("<<RunCurrentScript>>", intercept, True)
    wb.bind("<<DebugRun>>", intercept, True)
    wb.bind("<<DebugCurrentScript>>", intercept, True)


# -------------------------------------------------------------------------
# MENÚS DINÁMICOS
# -------------------------------------------------------------------------

def _crear_menus():
    wb = get_workbench()
    menu = wb.get_menu("tools")

    if not menu:
        wb.after(700, _crear_menus)
        return

    # Acción: Descargar ficheros
    def accion_descargar():
        mod = cargar_o_importar("descargar_ficheros")
        if mod and hasattr(mod, "main"):
            mod.main()

    # Acción: Corregir ejercicio
    def accion_corregir():
        mod = cargar_o_importar("corregir_ejercicio")
        if mod and hasattr(mod, "main"):
            mod.main()

    menu.add_separator()
    menu.add_command(label="📥 Descargar ficheros", command=accion_descargar)
    menu.add_command(label="✅ Corregir ejercicio", command=accion_corregir)


# -------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL (llamada por descargar_configuracion.py)
# -------------------------------------------------------------------------

def configurar(modulo):
    """configuracion.py se ejecuta dentro de mod_configuracion."""
    _config_cabecera()
    _config_vistas()
    _config_guardar_antes()
    _crear_menus()
