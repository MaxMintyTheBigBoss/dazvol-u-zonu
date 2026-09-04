# -*- coding: utf-8 -*-
"""
Runtime hook для PyInstaller: настройка путей к Tcl/Tk ДО загрузки tkinter.
Без этого tkinter не находит init.tcl и падает с "Can't find a usable init.tcl".
"""
import os
import sys

if getattr(sys, 'frozen', False):
    # PyInstaller распаковывает в sys._MEIPASS
    bundle_dir = sys._MEIPASS

    # Ищем Tcl/Tk в подпапках
    candidates = [
        os.path.join(bundle_dir, 'tcl', 'tcl8.6'),
        os.path.join(bundle_dir, 'tcl'),
        os.path.join(bundle_dir, 'tcl8.6'),
        os.path.join(bundle_dir, '_tcl_data'),
        bundle_dir,
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, 'init.tcl')):
            os.environ['TCL_LIBRARY'] = c
            break

    candidates_tk = [
        os.path.join(bundle_dir, 'tcl', 'tk8.6'),
        os.path.join(bundle_dir, 'tk8.6'),
        os.path.join(bundle_dir, '_tk_data'),
        bundle_dir,
    ]
    for c in candidates_tk:
        if os.path.exists(os.path.join(c, 'tk.tcl')):
            os.environ['TK_LIBRARY'] = c
            break

    # Добавляем пути к модулям
    sys.path.insert(0, bundle_dir)
    sys.path.insert(0, os.path.join(bundle_dir, 'permitunified'))
