# -*- coding: utf-8 -*-
"""
Runtime hook для PyInstaller: настройка путей к Tcl/Tk ДО загрузки tkinter.
Предотвращает ошибку "Can't find a usable init.tcl".
"""
import os
import sys

if getattr(sys, 'frozen', False):
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))

    # Расширенный список вариантов поиска init.tcl
    tcl_candidates = [
        os.path.join(bundle_dir, 'tcl', 'tcl8.6'),
        os.path.join(bundle_dir, '_tcl_data'),
        os.path.join(bundle_dir, 'tcl8.6'),
        os.path.join(bundle_dir, 'tcl'),
        bundle_dir,
    ]
    for path in tcl_candidates:
        if os.path.exists(os.path.join(path, 'init.tcl')):
            os.environ['TCL_LIBRARY'] = path
            break

    # Расширенный список вариантов поиска tk.tcl
    tk_candidates = [
        os.path.join(bundle_dir, 'tcl', 'tk8.6'),
        os.path.join(bundle_dir, '_tk_data'),
        os.path.join(bundle_dir, 'tk8.6'),
        os.path.join(bundle_dir, 'tk'),
        bundle_dir,
    ]
    for path in tk_candidates:
        if os.path.exists(os.path.join(path, 'tk.tcl')):
            os.environ['TK_LIBRARY'] = path
            break

    # Корректное добавление путей к модулям
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)
    
    pkg_dir = os.path.join(bundle_dir, 'permitunified')
    if os.path.exists(pkg_dir) and pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
