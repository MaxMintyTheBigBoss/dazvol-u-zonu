# -*- coding: utf-8 -*-
"""
Единое приложение «Генератор пропусков» — выбор процедуры + генерация.
Объединяет 14.3, 14.5, 19.17.1 в одно окно с выбором процедуры при запуске.
"""
import json
import os
import re
import sys
from typing import Optional
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# Импорт tkcalendar на уровне модуля — иначе падает при первом открытии календаря в скомпилированном exe
try:
    from tkcalendar import Calendar as _TkCalendar
    _TKCALENDAR_OK = True
except ImportError:
    _TKCALENDAR_OK = False
    _TkCalendar = None

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent))

try:
    from permitunified.generator import (
        generate_all, db_find, db_find_org, db_list_fio, db_list_org,
        UnifiedPermitDB, get_db_path,
        load_reference, filter_objects_by_districts
    )
    from permitunified.procedures import ProcedureConfig, list_procedures, get_procedure
    from permitunified.db import export_db_dialog
    from permitunified.settings import load_settings, save_settings
except ImportError:
    # Fallback для PyInstaller — загружаем напрямую
    import importlib.util
    def _load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    _gen = _load("permitunified.generator", str(Path(__file__).parent / "permitunified" / "generator.py"))
    _proc = _load("permitunified.procedures", str(Path(__file__).parent / "permitunified" / "procedures.py"))
    _db = _load("permitunified.db", str(Path(__file__).parent / "permitunified" / "db.py"))
    _set = _load("permitunified.settings", str(Path(__file__).parent / "permitunified" / "settings.py"))
    load_settings = _set.load_settings
    save_settings = _set.save_settings

    generate_all = _gen.generate_all
    db_find = _gen.db_find
    db_find_org = _gen.db_find_org
    db_list_fio = _gen.db_list_fio
    db_list_org = _gen.db_list_org
    UnifiedPermitDB = _gen.UnifiedPermitDB
    get_db_path = _gen.get_db_path
    load_reference = _gen.load_reference
    filter_objects_by_districts = _gen.filter_objects_by_districts
    ProcedureConfig = _proc.ProcedureConfig
    list_procedures = _proc.list_procedures
    get_procedure = _proc.get_procedure
    export_db_dialog = _db.export_db_dialog

from permit_update_gui import UpdateDialog

# Константы
APP_NAME = "dazvol_u_zonu"
APP_VERSION = "0.1.27"
APP_EXE_NAME = "dazvol_u_zonu.exe"


def _app_dir():
    """Папка, где лежит exe (или исходники при запуске из Python)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def installed_version():
    """Установленная версия: из version.json рядом с exe, иначе APP_VERSION.

    version.json пишется установщиком обновлений. Если файла нет
    (первый запуск, ручная распаковка) — берём версию из кода.
    """
    try:
        marker = _app_dir() / "version.json"
        if marker.exists():
            with open(marker, encoding="utf-8") as f:
                data = json.load(f)
            v = (data or {}).get("version")
            if v:
                return str(v)
    except Exception:
        pass
    return APP_VERSION
BG_COLOR = "#E6EBE0"
BTN_BG = "#CAD4CC"
BTN_ACTIVE = "#B3C3B8"

# Цвета для процедур
PROC_COLORS = {
    "14.3": BG_COLOR,
    "14.5": BG_COLOR,
    "19.17.1": BG_COLOR,
}


class CheckListbox(ttk.Frame):
    """Скроллируемый список чекбоксов для выбора районов/объектов."""

    def __init__(self, master, height=8, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.vars = {}

        # Безопасная прокрутка мышью при наведении
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def set_items(self, items: list):
        """items — список строк."""
        for w in self.inner.winfo_children():
            w.destroy()
        self.vars.clear()
        for item in items:
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(self.inner, text=item, variable=var)
            cb.pack(anchor="w", padx=4, pady=1)
            self.vars[item] = var

    def get_checked(self) -> list:
        return [item for item, var in self.vars.items() if var.get()]

    def set_checked(self, checked: list):
        checked_set = set(checked)
        for item, var in self.vars.items():
            var.set(item in checked_set)


class DateMask:
    """Маска ввода ДД.ММ.ГГГГ для обычного Entry (без календаря).

    Устанавливает точки после 2-й и 4-й цифры и держит курсор в конце.
    """

    LIMITS = (2, 2, 4)

    @classmethod
    def format_text(cls, text: str):
        """Возвращает (строка, позиция_курсора) для ввода ДД.ММ.ГГГГ."""
        if "." not in text:
            d = "".join(ch for ch in text if ch.isdigit())[:8]
            if len(d) > 2:
                s = d[:2] + "."
                if len(d) > 4:
                    s += d[2:4] + "." + d[4:]
                else:
                    s += d[2:]
                return s, len(s)
        parts = text.split(".")
        segs = []
        for i, lim in enumerate(cls.LIMITS):
            seg = "".join(c for c in (parts[i] if i < len(parts) else "") if c.isdigit())
            segs.append(seg[:lim])
        out = ""
        for i, seg in enumerate(segs):
            out += seg
            if i < 2:
                next_started = len(segs[i + 1]) > 0
                if len(seg) == cls.LIMITS[i] or next_started:
                    out += "."
        return out, len(out)

    @classmethod
    def parse(cls, text: str):
        """Разбирает ДД.ММ.ГГГГ в date или возвращает None."""
        from datetime import date
        t = (text or "").strip()
        if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", t):
            return None
        try:
            d, m, y = (int(x) for x in t.split("."))
            return date(y, m, d)
        except Exception:
            return None


# Соответствие «подписант -> район по умолчанию» (из предложений пользователя).
# У Шабловского В.О., Соломейчука А.В., Путьковой Т.М. района нет.
SIGNER_DISTRICT = {
    "Главный специалист Гвоздарев А.А.": "Кормянский",
    "Главный специалист Геращенко Г.Н.": "Чечерский",
    "Главный специалист Першко А.С.": "Ветковский",
    "Главный специалист Одиноченко И.В.": "Добрушский",
    "Главный специалист Колесан А.И.": "Брагинский",
    "Главный специалист Новик П.Н.": "Хойникский",
    "Главный специалист Курило А.В.": "Наровлянский",
}


def cap_word(s: str) -> str:
    """Делает первую букву заглавной, остальные строчными (для Ф.И.О.)."""
    s = (s or "").strip()
    if not s:
        return ""
    return s[0].upper() + s[1:].lower()


def cap_id(s: str) -> str:
    """Приводит личный/гос. номер к верхнему регистру."""
    return (s or "").strip().upper()


def cap_first(s: str) -> str:
    """Делает заглавной ТОЛЬКО первую букву, остальное не трогает.

    Для полей «Организация» и «Марка-модель»: если пользователь набрал
    часть букв заглавными, они такими и остаются.
    """
    s = (s or "").strip()
    if not s:
        return ""
    return s[0].upper() + s[1:]


def _clip_copy(event):
    """Ctrl+C: копирует выделение в буфер обмена."""
    w = event.widget
    try:
        if w.selection_present():
            w.clipboard_clear()
            w.clipboard_append(w.selection_get())
    except Exception:
        pass
    return "break"


def _clip_cut(event):
    """Ctrl+X: копирует выделение и удаляет его."""
    w = event.widget
    try:
        if w.selection_present():
            text = w.selection_get()
            w.clipboard_clear()
            w.clipboard_append(text)
            w.delete("sel.first", "sel.last")
    except Exception:
        pass
    return "break"


def _clip_paste(event):
    """Ctrl+V: вставляет текст из буфера обмена в позицию курсора."""
    w = event.widget
    try:
        text = w.clipboard_get()
    except Exception:
        return "break"
    try:
        if w.selection_present():
            w.delete("sel.first", "sel.last")
        w.insert("insert", text)
    except Exception:
        pass
    return "break"


def _clip_select_all(event):
    """Ctrl+A: выделяет всё содержимое поля."""
    w = event.widget
    try:
        w.selection_range(0, "end")
        w.icursor("end")
    except Exception:
        pass
    return "break"


def _clip_dispatch(event):
    """Единый перехват Ctrl+C/V/X/A по ФИЗИЧЕСКОМУ keycode.

    На Windows keysym для Ctrl+буква при не-латинской раскладке часто
    приходит как '??', поэтому ориентируемся на keycode (он одинаков
    для любой раскладки) и на модификатор Control (state & 4).
    """
    w = getattr(event, "widget", None)
    if w is None or not hasattr(w, "insert"):
        return None
    if not (event.state & 4):  # Control не нажат
        return None
    code = event.keycode
    # 67=C, 86=V, 88=X, 65=A — физические клавиши
    if code == 67:
        return _clip_copy(event)
    if code == 86:
        return _clip_paste(event)
    if code == 88:
        return _clip_cut(event)
    if code == 65:
        return _clip_select_all(event)
    # запасной путь: если keycode не пришёл, пробуем keysym
    ks = (event.keysym or "").lower()
    if ks == "c":
        return _clip_copy(event)
    if ks == "v":
        return _clip_paste(event)
    if ks == "x":
        return _clip_cut(event)
    if ks == "a":
        return _clip_select_all(event)
    return None


def _bind_clipboard_on(widget):
    """Навешивает Ctrl+C/V/X/A прямо на конкретный виджет ввода."""
    pairs = [
        ("<Control-c>", _clip_copy), ("<Control-C>", _clip_copy),
        ("<Control-v>", _clip_paste), ("<Control-V>", _clip_paste),
        ("<Control-x>", _clip_cut), ("<Control-X>", _clip_cut),
        ("<Control-a>", _clip_select_all), ("<Control-A>", _clip_select_all),
        ("<Control-Insert>", _clip_copy), ("<Shift-Insert>", _clip_paste),
    ]
    for seq, fn in pairs:
        try:
            widget.bind(seq, fn)
        except Exception:
            pass


def install_clipboard_bindings(widget):
    """Явно включает Ctrl+C/V/X/A во ВСЕХ полях ввода приложения.

    Навешиваем через bind_class на уровне этого Tk-приложения (единственный
    корневой виджет) — так привязка работает и для ttk.Entry, и для
    ttk.Combobox, и для tk.Entry, созданных в любой момент.
    """
    pairs = [
        ("<Control-c>", _clip_copy), ("<Control-C>", _clip_copy),
        ("<Control-v>", _clip_paste), ("<Control-V>", _clip_paste),
        ("<Control-x>", _clip_cut), ("<Control-X>", _clip_cut),
        ("<Control-a>", _clip_select_all), ("<Control-A>", _clip_select_all),
        ("<Control-Insert>", _clip_copy), ("<Shift-Insert>", _clip_paste),
        ("<Control-KP_Insert>", _clip_copy), ("<Shift-KP_Insert>", _clip_paste),
    ]
    for cls in ("Entry", "TEntry", "TCombobox", "Text"):
        for seq, fn in pairs:
            try:
                widget.bind_class(cls, seq, fn, add="+")
            except Exception:
                pass
    widget.bind_all("<Control-KeyPress>", _clip_dispatch, add="+")


def _upper_word(cls, text):
    """Обработчик FocusOut для Ф.И.О.: первая заглавная, остальное строчное."""
    return cap_word(text)


def bind_enter_as_tab(widget):
    """Enter в поле = Tab: переход к следующему виджету ввода.

    tk_focusNext() для ttk-виджетов часто возвращает сам виджет, поэтому
    строим порядок обхода явно: собираем все поля ввода текущей вкладки
    и переходим к следующему по списку.
    """
    def on_return(event):
        try:
            order = _focus_order(event.widget)
            if not order:
                return "break"
            cur = event.widget
            if cur in order:
                nxt = order[(order.index(cur) + 1) % len(order)]
            else:
                nxt = order[0]
            nxt.focus_set()
            try:
                nxt.selection_range(0, "end")
            except Exception:
                pass
        except Exception:
            pass
        return "break"
    widget.bind("<Return>", on_return)


def _focus_order(widget):
    """Список полей ввода в текущем контейнере, в порядке создания.

    Для главного окна — поля активной вкладки ноутбука; для диалога
    (Toplevel без ноутбука) — все поля этого диалога.
    """
    try:
        top = widget.winfo_toplevel()
        nb = getattr(top, "nb", None)
        if nb is not None:
            sel = nb.select()
            tab = nb.nametowidget(sel) if sel else nb
            order = _walk_entries(tab)
            if order:
                return order
        return _walk_entries(top)
    except Exception:
        return []


def _walk_entries(parent):
    """Рекурсивно обходит виджеты и отдаёт поля ввода в порядке упаковки."""
    result = []
    try:
        children = parent.winfo_children()
    except Exception:
        return result
    for ch in children:
        cls = ch.winfo_class()
        if cls in ("Entry", "TEntry", "TCombobox", "Text"):
            try:
                if ch.cget("state") not in ("disabled",):
                    result.append(ch)
            except Exception:
                result.append(ch)
        else:
            result.extend(_walk_entries(ch))
    return result


def _safe_focus(widget):
    """Ставит фокус на виджет, если он ещё существует (не уничтожен)."""
    try:
        if widget is not None and widget.winfo_exists():
            widget.focus_set()
    except Exception:
        pass


def attach_date_mask(entry, var):
    """Включает маску ДД.ММ.ГГГГ на обычном ttk.Entry."""
    SKIP = (
        "Left", "Right", "Home", "End", "Up", "Down", "Tab",
        "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    )

    def on_type(event):
        if event.keysym in SKIP:
            return
        formatted, pos = DateMask.format_text(var.get())
        if formatted != var.get():
            var.set(formatted)
        try:
            entry.icursor(pos)
        except Exception:
            pass

    entry.bind("<KeyRelease>", on_type)
    return entry


class DateEntryWithCalendar(ttk.Frame):
    """Поле даты с маской ДД.ММ.ГГГГ и кнопкой календаря."""

    def __init__(self, master, label: str, var: tk.StringVar, width=18, **kw):
        super().__init__(master, **kw)
        self.var = var
        if label:
            ttk.Label(self, text=label).pack(side="left", padx=(0, 4))
        self.entry = ttk.Entry(self, textvariable=var, width=width)
        self.entry.pack(side="left")
        self.entry.bind("<KeyRelease>", self._on_type)
        ttk.Button(self, text="📅", width=3, command=self._open_calendar).pack(side="left", padx=2)

    _DATE_LIMITS = (2, 2, 4)  # день, месяц, год

    @classmethod
    def _format_date(cls, text: str):
        """Приводит ввод к виду ДД.ММ.ГГГГ.

        Возвращает (строка, позиция_курсора). Разбор идёт ПО СЕКЦИЯМ, разделённым
        точками: цифры из разных секций не склеиваются. Именно поэтому ввод
        "01" + "0" даёт "01.0" (ноль попадает в месяц), а не "01." с потерей цифры.
        """
        # Слитный ввод без точек (вставка из буфера, быстрый набор): DDMMYYYY
        if "." not in text:
            d = "".join(ch for ch in text if ch.isdigit())[:8]
            if len(d) > 2:
                s = d[:2] + "."
                if len(d) > 4:
                    s += d[2:4] + "." + d[4:]
                else:
                    s += d[2:]
                return s, len(s)
        parts = text.split(".")
        segs = []
        for i, lim in enumerate(cls._DATE_LIMITS):
            seg = "".join(c for c in (parts[i] if i < len(parts) else "") if c.isdigit())
            segs.append(seg[:lim])
        out = ""
        for i, seg in enumerate(segs):
            out += seg
            if i < 2:
                next_started = len(segs[i + 1]) > 0
                if len(seg) == cls._DATE_LIMITS[i] or next_started:
                    out += "."
        return out, len(out)

    def _on_type(self, event):
        """Маска даты ДД.ММ.ГГГГ: точки ставятся автоматически, курсор — в конец.

        Вызывается на <KeyRelease>, когда Tk уже вставил символ. Курсор всегда
        переносится в конец строки, поэтому следующая цифра попадает в нужную
        секцию, а не в середину (прежний баг: курсор оставался в центре).
        """
        if event.keysym in (
            "Left", "Right", "Home", "End", "Up", "Down", "Tab",
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
        ):
            return
        formatted, pos = self._format_date(self.var.get())
        if formatted != self.var.get():
            self.var.set(formatted)
        self.entry.icursor(pos)

    def _open_calendar(self):
        if not _TKCALENDAR_OK:
            messagebox.showerror("Ошибка", "Модуль tkcalendar не установлен")
            return
        top = tk.Toplevel(self)
        top.title("Выбор даты")
        top.transient(self)
        top.grab_set()
        # Центрируем календарь относительно родителя или главного окна
        top.update_idletasks()
        parent_app = self.master
        while parent_app and not isinstance(parent_app, tk.Tk):
            parent_app = parent_app.master
        if parent_app and isinstance(parent_app, tk.Tk):
            x = parent_app.winfo_rootx() + max(0, (parent_app.winfo_width() - top.winfo_reqwidth()) // 2)
            y = parent_app.winfo_rooty() + max(0, (parent_app.winfo_height() - top.winfo_reqheight()) // 2)
            sw, sh = parent_app.winfo_screenwidth(), parent_app.winfo_screenheight()
            x = max(10, min(x, sw - top.winfo_reqwidth() - 10))
            y = max(10, min(y, sh - top.winfo_reqheight() - 10))
            top.geometry(f"+{x}+{y}")
        cal = _TkCalendar(top, date_pattern="dd.mm.yyyy", firstweekday="monday")
        cal.pack(padx=10, pady=10)

        def on_select():
            self.var.set(cal.get_date())
            top.destroy()

        ttk.Button(top, text="Выбрать", command=on_select).pack(pady=5)


class MainMenuFrame(ttk.Frame):
    """Главное меню: выбор процедуры + управление БД + обновления + о программе.

    Реализован как Frame (НЕ Toplevel) внутри PermitApp. Это полностью исключает
    проблемы с grab_set/wait_window, которые приводили к закрытию приложения.
    """

    def __init__(self, master, app: "PermitApp"):
        super().__init__(master, padding=16)
        self.app = app
        self._build()

    def _build(self):
        ttk.Label(self, text="Выбор процедуры", font=("Roboto", 16, "bold")).pack(pady=(0, 8))

        # Кнопки процедур
        procedures = list_procedures()
        procedures.sort(key=lambda p: p.code)
        proc_frame = ttk.Frame(self)
        proc_frame.pack(fill="both", expand=True, pady=8)

        for p in procedures:
            color = PROC_COLORS.get(p.code, "#999")
            fg = "white" if color not in ("#E6EBE0", "#FDD9B5", "#D4FCEE") else "black"
            btn = tk.Button(
                proc_frame,
                text=p.code,
                font=("Roboto", 18, "bold"),
                bg=color,
                fg=fg,
                activebackground=color,
                activeforeground=fg,
                relief="flat",
                cursor="hand2",
                height=2,
                command=lambda c=p.code: self.app.open_procedure(c),
            )
            btn.pack(fill="x", expand=True, padx=4, pady=4)

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=10)

        # Кнопки действий
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=4)

        ttk.Button(actions, text="📤 Выгрузить БД",
                   command=self.app.action_export_db).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(actions, text="📥 Загрузить БД",
                   command=self.app.action_import_db).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(actions, text="🔄 Обновления",
                   command=self.app.action_check_updates).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(actions, text="ℹ️ О программе",
                   command=self.app.action_about).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(actions, text="⚙️ Настройки",
                   command=self.app.action_settings).pack(side="left", fill="x", expand=True, padx=2)

        ttk.Button(self, text="Выход", command=self.app.action_exit).pack(fill="x", pady=(8, 0))


class PermitApp(tk.Tk):
    """Главное окно приложения.

    Архитектура: в одном Tk-окне последовательно показываются
    MainMenuFrame (главное меню) и ProcedureFrame (одна из процедур).
    Никаких Toplevel/grab_set/wait_window — это устраняет проблему
    «закрытия приложения при нажатии кнопки».
    """

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("900x750")
        self.minsize(850, 700)
        self.configure(bg=BG_COLOR)

        self.current_frame: Optional[ttk.Frame] = None

        # Пользовательские настройки (кому на подписание, район по умолчанию)
        try:
            self.settings = load_settings()
        except Exception:
            self.settings = {}

        # Явные привязки Ctrl+C/V/X/A во всех полях ввода
        try:
            install_clipboard_bindings(self)
        except Exception:
            pass

        # Ensure window is shown
        self._set_icon()
        self.deiconify()
        self.update_idletasks()
        
        self.show_menu()

    # ------------------------------------------------------------------
    # Главное меню
    # ------------------------------------------------------------------
    def _set_icon(self):
        """Ставит иконку окна из app.ico (рядом с exe или исходниками)."""
        try:
            if getattr(sys, "frozen", False):
                base = Path(sys.executable).parent
            else:
                base = Path(__file__).parent
            ico = base / "app.ico"
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

    def show_menu(self):
        """Показать главное меню выбора процедуры."""
        self._clear_content()
        self.procedure_code = None
        self.procedure = None
        self.configure(bg=BG_COLOR)
        self.title(APP_NAME)
        self.current_frame = MainMenuFrame(self, self)
        self.current_frame.pack(fill="both", expand=True)
        self._center_window()

    def _center_window(self):
        """Центрирует главное окно на экране."""
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
    def _center_dialog_on_main_window(self, dialog):
        """Центрирует диалог (Toplevel) относительно главного окна или по центру экрана."""
        dialog.update_idletasks()
        dlg_w = dialog.winfo_reqwidth()
        dlg_h = dialog.winfo_reqheight()
        main_w = self.winfo_width() or 900
        main_h = self.winfo_height() or 750
        x = self.winfo_rootx() + (main_w - dlg_w) // 2
        y = self.winfo_rooty() + (main_h - dlg_h) // 2
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(10, min(x, sw - dlg_w - 10))
        y = max(10, min(y, sh - dlg_h - 10))
        dialog.geometry(f"+{x}+{y}")



    # ------------------------------------------------------------------
    # Действия меню
    # ------------------------------------------------------------------
    def open_procedure(self, code: str):
        """Открыть форму выбранной процедуры."""
        self.procedure_code = code
        self.procedure = get_procedure(code)
        self._clear_content()
        self.configure(bg=PROC_COLORS.get(code, BG_COLOR))
        self.title(f"{APP_NAME} — {self.procedure.name}")

        # Инициализация переменных под текущую процедуру
        self._init_variables()

        # Создаём контейнер для UI процедуры
        proc_frame = ttk.Frame(self)
        proc_frame.pack(fill="both", expand=True)
        self.current_frame = proc_frame

        # Строим UI процедуры внутри proc_frame
        self._build_ui(proc_frame)

    def change_procedure(self):
        """Кнопка 'Сменить процедуру' — возврат в меню."""
        self.show_menu()

    def action_exit(self):
        """Кнопка 'Выход'."""
        self.destroy()

    def action_export_db(self):
        try:
            export_db_dialog(self, get_db_path(),
                             f"permits_export_{datetime.now():%Y-%m-%d}.json")
        except Exception as e:
            messagebox.showerror("Выгрузка БД", f"Ошибка: {e}", parent=self)

    def action_import_db(self):
        self._import_db()

    def action_check_updates(self):
        try:
            dlg_upd = UpdateDialog(self, installed_version(), APP_EXE_NAME)
            self.wait_window(dlg_upd)
        except Exception as e:
            messagebox.showerror("Обновления", f"Ошибка: {e}", parent=self)

    def action_about(self):
        self._show_about()

    def action_settings(self):
        """Окно настроек: подписант по умолчанию, район по умолчанию."""
        dlg = SettingsDialog(self, self.settings or {}, get_procedure)
        self.wait_window(dlg)
        if dlg.result is not None:
            self.settings = dlg.result
            try:
                save_settings(self.settings)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Служебные
    # ------------------------------------------------------------------
    def _clear_content(self):
        if self.current_frame is not None:
            try:
                self.current_frame.destroy()
            except Exception:
                pass
            self.current_frame = None

    def _import_db(self):
        path = filedialog.askopenfilename(
            title="Выберите файл БД (JSON)",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        try:
            import json as _json
            with open(path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            if not isinstance(data, list):
                data = [data]
            db = UnifiedPermitDB()
            imported = 0
            for rec in data:
                proc_code = rec.get("procedure_code") or rec.get("procedure") or "14.3"
                search_type = rec.get("search_type") or (
                    "org" if rec.get("org") or rec.get("organization") else "fio"
                )
                db.upsert(rec, proc_code, search_type)
                imported += 1
            db.close()
            messagebox.showinfo("Импорт БД", f"Импортировано записей: {imported}\n\nФайл: {path}", parent=self)
        except Exception as e:
            messagebox.showerror("Ошибка импорта БД", f"Не удалось импортировать:\n{e}", parent=self)

    def _show_about(self):
        about = (
            f"{APP_NAME}\n"
            f"Версия {installed_version()}\n"
            f"Файл: {APP_EXE_NAME}\n\n"
            f"Единый генератор пропусков по процедурам:\n"
            f"  • 14.3 — Пребывание на территории зоны\n"
            f"  • 14.5 — Вывоз имущества\n"
            f"  • 19.17.1 — Въезд транспорта / Работы\n\n"
            f"Возможности:\n"
            f"  • Генерация заявлений и пропусков (.docx, А6)\n"
            f"  • Единая SQLite база данных (все процедуры)\n"
            f"  • Экспорт БД в JSON / CSV / Excel\n"
            f"  • Импорт БД из JSON\n"
            f"  • Обновление через GitHub или из локального .zip\n\n"
            f"Создатель: Соломейчук Алексей\n"
            f"Email: al.vl.solo@yandex.by\n\n"
            f"Репозиторий: github.com/MaxMintyTheBigBoss/dazvol-u-zonu\n"
            f"© 2026"
        )
        messagebox.showinfo("О программе", about, parent=self)

    def _init_variables(self):
        self.var_last_name = tk.StringVar()
        self.var_first_name = tk.StringVar()
        self.var_middle_name = tk.StringVar()
        self.var_birth_date = tk.StringVar()
        self.var_id_number = tk.StringVar()
        self.var_goal = tk.StringVar()
        self.var_date_from = tk.StringVar()
        self.var_date_to = tk.StringVar()
        self.var_issued_by = tk.StringVar()
        self.var_car_make = tk.StringVar()
        self.var_car_number = tk.StringVar()
        self.var_objects = tk.StringVar()
        self.var_custom_object = tk.StringVar()
        self.var_include_pgrez = tk.BooleanVar(value=False)
        self.var_cargo = tk.StringVar()
        self.var_output = tk.StringVar(value=self._default_output())

        self.var_org_info = tk.StringVar()
        self.var_org_short = tk.StringVar()
        self.var_org_rep_last = tk.StringVar()
        self.var_org_rep_first = tk.StringVar()
        self.var_org_rep_middle = tk.StringVar()

        self.persons = []
        self.vehicles = []

    def _default_output(self):
        if getattr(sys, 'frozen', False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).parent.parent
        return str(base / "output")

    def _build_ui(self, parent):
            style = ttk.Style(parent)
            style.theme_use("clam")
            bg_proc = PROC_COLORS.get(self.procedure_code, BG_COLOR)
            style.configure("TFrame", background=bg_proc)
            style.configure("TLabel", background=bg_proc)
            style.configure("TCheckbutton", background=bg_proc)
            style.configure("TNotebook", background=bg_proc)
            style.configure("TNotebook.Tab", padding=(12, 6), font=("", 11, "bold"))
            style.map("TNotebook.Tab", background=[("selected", BTN_ACTIVE)], foreground=[("selected", "black")])
            style.configure(".", font=("Roboto", 13))
            style.configure("TButton", font=("Roboto", 11, "bold"))
            style.map("TButton", background=[("active", BTN_ACTIVE), ("!active", BTN_BG)])

            header = ttk.Frame(parent)
            header.pack(fill="x", padx=10, pady=8)
            ttk.Label(header, text=self.procedure.name, font=("Roboto", 14, "bold"),
                      foreground=PROC_COLORS.get(self.procedure_code, "black")).pack(side="left", padx=10)
            ttk.Button(header, text="← Сменить процедуру", command=self._change_procedure).pack(side="right", padx=10)

            self.nb = ttk.Notebook(parent)
            self.nb.pack(fill="both", expand=True, padx=8, pady=4)

            tab1 = ttk.Frame(self.nb)
            self.nb.add(tab1, text="1. Заявитель / Организация")
            self._build_tab_applicant(tab1)

            # Вкладка 2 скрыта для 14.5
            if self.procedure.has_individual_permits and self.procedure_code != "14.5":
                tab2 = ttk.Frame(self.nb)
                self.nb.add(tab2, text="2. Лица / Пассажиры")
                self._build_tab_persons(tab2)

            # Вкладка 3 скрыта для 14.5
            if self.procedure.has_transport_permits and self.procedure_code != "14.5":
                tab3 = ttk.Frame(self.nb)
                self.nb.add(tab3, text="3. Автомобили")
                self._build_tab_vehicles(tab3)

            tab4 = ttk.Frame(self.nb)
            self.nb.add(tab4, text="4. Районы / Объекты")
            self._build_tab_districts(tab4)

            if self.procedure.has_cargo_permit:
                tab5 = ttk.Frame(self.nb)
                self.nb.add(tab5, text="5. Груз")
                self._build_tab_cargo(tab5)

            self._build_buttons(parent)
            self.status_bar = ttk.Label(parent, text="Готово", relief="sunken", anchor="w")
            self.status_bar.pack(fill="x", padx=8, pady=(0, 8))

    def _change_procedure(self):
        """Кнопка 'Сменить процедуру' — возврат в меню (из заголовка)."""
        self.show_menu()

    def _db_fill_from_record(self, rec, overwrite=False):
        """Заполняет форму данными записи из базы.

        Кнопка «Найти в базе» вызывает с overwrite=True — заполняются ВСЕ
        вкладки и поля, сохранённые при первой выдаче пропуска. Автоподстановка
        при уходе с поля использует overwrite=False: уже введённое не затирается.
        """
        if not rec:
            return []

        def put(var, key):
            val = str(rec.get(key, "") or "").strip()
            if not val:
                return None
            if not overwrite and var.get().strip():
                return None
            var.set(val)
            return val

        filled = []
        if self.procedure_code == "19.17.1":
            for var, key in (
                (self.var_org_info, "org_info"),
                (self.var_org_short, "org_short"),
                (self.var_org_rep_last, "org_rep_last"),
                (self.var_org_rep_first, "org_rep_first"),
                (self.var_org_rep_middle, "org_rep_middle"),
            ):
                if put(var, key):
                    filled.append(key)
        else:
            for var, key in (
                (self.var_last_name, "last_name"),
                (self.var_first_name, "first_name"),
                (self.var_middle_name, "middle_name"),
                (self.var_birth_date, "birth_date"),
                (self.var_id_number, "id_number"),
                (self.var_car_make, "car_make"),
                (self.var_car_number, "car_number"),
            ):
                if put(var, key):
                    filled.append(key)

        # Цель — только если поле редактируемое (не goal_fixed)
        if not self.procedure.goal_fixed and put(self.var_goal, "goal"):
            filled.append("goal")

        # Груз (вкладка 5 у 14.5)
        if self.procedure.has_cargo_permit and put(self.var_cargo, "cargo"):
            filled.append("cargo")

        # Срок действия
        if put(self.var_date_from, "date_from"):
            filled.append("date_from")
        if put(self.var_date_to, "date_to"):
            filled.append("date_to")

        # Кому на подписание
        if put(self.var_issued_by, "issued_by"):
            filled.append("issued_by")

        # Районы (вкладка 4)
        districts = rec.get("districts") or []
        if districts and hasattr(self, "district_vars"):
            for d, var in self.district_vars.items():
                if d in districts:
                    var.set(True)
            filled.append("districts")
            if hasattr(self, "_refresh_objects"):
                self._refresh_objects()

        # Объекты (вкладка 4)
        if put(self.var_custom_object, "custom_object"):
            filled.append("custom_object")
        objects = rec.get("objects") or []
        if objects and hasattr(self, "objects_clb"):
            try:
                self.objects_clb.set_checked(list(objects))
                filled.append("objects")
            except Exception:
                pass
        if rec.get("include_pgrez"):
            self.var_include_pgrez.set(True)
            filled.append("include_pgrez")

        # Сопровождающие и машины — списки целиком
        persons = rec.get("persons") or []
        if persons and hasattr(self, "persons") and (overwrite or not self.persons):
            self.persons = list(persons)
            if hasattr(self, "persons_listbox"):
                self._refresh_persons_list()
            filled.append("persons")
        vehicles = rec.get("vehicles") or []
        if vehicles and hasattr(self, "vehicles") and (overwrite or not self.vehicles):
            self.vehicles = list(vehicles)
            if hasattr(self, "vehicles_listbox"):
                self._refresh_vehicles_list()
            filled.append("vehicles")

        return filled

    def _autofill_applicant(self, event=None):
        """Ищет заявителя в базе по ФИО (или организации) и заполняет форму."""
        try:
            if self.procedure_code == "19.17.1":
                key = (self.var_org_short.get() or self.var_org_info.get()).strip()
                if len(key) < 3:
                    return
                rec = db_find_org(key, self.procedure_code)
            else:
                parts = [self.var_last_name.get().strip(),
                         self.var_first_name.get().strip(),
                         self.var_middle_name.get().strip()]
                key = " ".join(p for p in parts if p)
                if len(parts[0]) < 2:
                    return
                rec = db_find(key, self.procedure_code)
            if not rec:
                return
            filled = self._db_fill_from_record(rec)
            if filled:
                self.status_bar.config(
                    text="Данные подставлены из базы: " + ", ".join(filled))
        except Exception:
            pass

    def _db_lookup_record(self):
        """Ищет запись в базе по данным формы. Возвращает (record, key) или (None, key).

        Вынесено отдельно, потому что результат поиска нужен и автоподстановке,
        и кнопке «Найти в базе» — сравнивать поля до/после нельзя: при успешном
        поиске имя уже введено пользователем и не меняется.
        """
        if self.procedure_code == "19.17.1":
            key = (self.var_org_info.get() or self.var_org_short.get()).strip()
            if len(key) < 3:
                return None, key
            return db_find_org(key, self.procedure_code), key

        parts = [self.var_last_name.get().strip(),
                 self.var_first_name.get().strip(),
                 self.var_middle_name.get().strip()]
        key = " ".join(p for p in parts if p)
        if len(parts[0]) < 2:
            return None, key
        return db_find(key, self.procedure_code), key

    def _on_find_in_db(self):
        """Кнопка «Найти в базе»: ищем и, если не нашли, сообщаем."""
        try:
            rec, key = self._db_lookup_record()
        except Exception as e:
            messagebox.showerror("Поиск в базе", "Ошибка поиска:\n%s" % e, parent=self)
            return
        if not rec:
            messagebox.showinfo(
                "Поиск в базе",
                "Совпадений не найдено.\n\n"
                "Искомый ключ: %s\n\n"
                "Поиск идёт по фамилии, имени и отчеству целиком (для организаций — по наименованию)\n"
                "среди ранее выданных пропусков по этой же процедуре." % (key or "—"),
                parent=self)
            return
        filled = self._db_fill_from_record(rec, overwrite=True)
        if filled:
            self.status_bar.config(
                text="Из базы заполнено: " + ", ".join(filled))
        else:
            self.status_bar.config(text="Запись найдена, но данных для подстановки нет")
    def _build_tab_applicant(self, parent):
        pad = {"padx": 6, "pady": 4}
        r = 0

        first_focus_widget = None

        if self.procedure_code == "19.17.1":
            # Организация (краткое наименование) — одна строка
            ttk.Label(parent, text="Организация (краткое наименование):").grid(row=r, column=0, sticky="w", **pad)
            e_org = ttk.Entry(parent, textvariable=self.var_org_info, width=60)
            e_org.grid(row=r, column=1, columnspan=3, sticky="ew", **pad); r += 1
            bind_enter_as_tab(e_org)
            e_org.bind("<FocusOut>", self._autofill_applicant)
            # Организация: первая буква заглавная
            e_org.bind("<FocusOut>", lambda ev: self.var_org_info.set(cap_first(self.var_org_info.get())), add="+")
            first_focus_widget = e_org
            ttk.Button(parent, text="🔍 Найти в базе", command=self._on_find_in_db).grid(
                row=r, column=0, columnspan=2, sticky="w", padx=6, pady=4); r += 1
            # Удалено: "Организация (краткое)"
            # Закомментировано: Представитель организации, Фамилия, Имя, Отчество
            # ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
            # ttk.Label(parent, text="Представитель организации:", font=("", 11, "bold")).grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
            # ttk.Label(parent, text="Фамилия:").grid(row=r, column=0, sticky="w", **pad)
            # ttk.Entry(parent, textvariable=self.var_org_rep_last, width=30).grid(row=r, column=1, sticky="ew", **pad)
            # ttk.Label(parent, text="Имя:").grid(row=r, column=2, sticky="w", **pad)
            # ttk.Entry(parent, textvariable=self.var_org_rep_first, width=30).grid(row=r, column=3, sticky="ew", **pad); r += 1
            # ttk.Label(parent, text="Отчество:").grid(row=r, column=0, sticky="w", **pad)
            # ttk.Entry(parent, textvariable=self.var_org_rep_middle, width=30).grid(row=r, column=1, sticky="ew", **pad); r += 1
        else:
            ttk.Label(parent, text="Фамилия:", font=("", 11, "bold")).grid(row=r, column=0, sticky="w", **pad)
            e_last = ttk.Entry(parent, textvariable=self.var_last_name, width=30)
            e_last.grid(row=r, column=1, sticky="ew", **pad)
            ttk.Label(parent, text="Имя:").grid(row=r, column=2, sticky="w", **pad)
            e_first = ttk.Entry(parent, textvariable=self.var_first_name, width=30)
            e_first.grid(row=r, column=3, sticky="ew", **pad); r += 1
            ttk.Label(parent, text="Отчество:").grid(row=r, column=0, sticky="w", **pad)
            e_middle = ttk.Entry(parent, textvariable=self.var_middle_name, width=30)
            e_middle.grid(row=r, column=1, sticky="ew", **pad)
            ttk.Label(parent, text="Дата рождения:").grid(row=r, column=2, sticky="w", **pad)
            e_birth = ttk.Entry(parent, textvariable=self.var_birth_date, width=30)
            e_birth.grid(row=r, column=3, sticky="ew", **pad)
            attach_date_mask(e_birth, self.var_birth_date); r += 1
            ttk.Label(parent, text="Личный номер:").grid(row=r, column=0, sticky="w", **pad)
            e_id = ttk.Entry(parent, textvariable=self.var_id_number, width=30)
            e_id.grid(row=r, column=1, sticky="ew", **pad)
            e_id.bind("<FocusOut>", self._autofill_applicant)

            # Ф.И.О.: первая буква заглавная при уходе с поля
            for _e, _v in ((e_last, self.var_last_name), (e_first, self.var_first_name), (e_middle, self.var_middle_name)):
                _e.bind("<FocusOut>", lambda ev, v=_v: v.set(cap_word(v.get())), add="+")
            # Личный номер — всегда заглавными
            e_id.bind("<FocusOut>", lambda ev: self.var_id_number.set(cap_id(self.var_id_number.get())), add="+")
            # Enter = Tab по всем полям заявителя
            for _e in (e_last, e_first, e_middle, e_birth, e_id):
                bind_enter_as_tab(_e)
            first_focus_widget = e_last
            # Кнопка поиска — на своей строке, чтобы её не перекрывали другие поля
            ttk.Button(parent, text="🔍 Найти в базе", command=self._on_find_in_db).grid(
                row=r, column=2, columnspan=2, sticky="w", padx=6, pady=4); r += 1

        ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        ttk.Label(parent, text="Цель въезда:", font=("", 11, "bold")).grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
        if self.procedure.goal_fixed:
            self.var_goal.set(self.procedure.goal_fixed)
            ttk.Label(parent, text=self.procedure.goal_fixed, foreground="gray").grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
        elif self.procedure.goal_options:
            # Первая цель — по умолчанию (для 19.17.1 «для осуществления служебной деятельности»)
            if not self.var_goal.get().strip():
                self.var_goal.set(self.procedure.goal_options[0])
            cb_goal = ttk.Combobox(parent, textvariable=self.var_goal, values=self.procedure.goal_options, width=55)
            cb_goal.grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
            bind_enter_as_tab(cb_goal)
        else:
            e_goal = ttk.Entry(parent, textvariable=self.var_goal, width=60)
            e_goal.grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
            bind_enter_as_tab(e_goal)

        ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        ttk.Label(parent, text="Срок действия:", font=("", 11, "bold")).grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
        ttk.Label(parent, text="С:").grid(row=r, column=0, sticky="w", **pad)
        DateEntryWithCalendar(parent, "", self.var_date_from).grid(row=r, column=1, sticky="ew", **pad)
        ttk.Label(parent, text="По:").grid(row=r, column=2, sticky="w", **pad)
        DateEntryWithCalendar(parent, "", self.var_date_to).grid(row=r, column=3, sticky="ew", **pad); r += 1

        ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        ttk.Label(parent, text="Кому на подписание:", font=("", 11, "bold")).grid(row=r, column=0, sticky="w", **pad)
        # Подписант по умолчанию — из настроек, иначе первый из списка
        _default_signer = (self.settings or {}).get("default_signer", "") or ""
        if _default_signer not in self.procedure.signers:
            _default_signer = self.procedure.signers[0] if self.procedure.signers else ""
        self.var_issued_by = tk.StringVar(value=_default_signer)
        cb_signer = ttk.Combobox(parent, textvariable=self.var_issued_by, values=self.procedure.signers, width=55, state="readonly")
        cb_signer.grid(row=r, column=1, columnspan=3, sticky="ew", **pad)
        bind_enter_as_tab(cb_signer)
        # Смена подписанта -> автоматически отмечается «его» район
        cb_signer.bind("<<ComboboxSelected>>", lambda ev: self._apply_signer_district(self.var_issued_by.get()))

        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

        # Автофокус на первом поле ввода (безопасно: виджет может быть уже уничтожен)
        if first_focus_widget is not None:
            self.after(80, lambda w=first_focus_widget: _safe_focus(w))
        # Район по умолчанию — если подписант по умолчанию задан в настройках
        if _default_signer:
            self._apply_signer_district(_default_signer)

    def _apply_signer_district(self, signer: str):
        """Отмечает «родной» район выбранного подписанта (снимая прежние отметки).

        Соответствие подписант -> район задано в SIGNER_DISTRICT. Для подписантов
        без закреплённого района ничего не меняем.
        """
        if not hasattr(self, "district_vars") or not self.district_vars:
            return
        district = SIGNER_DISTRICT.get(signer or "")
        if not district:
            return
        for name, var in self.district_vars.items():
            var.set(name == district)
        self._refresh_objects()

    def _apply_default_district(self):
        """Отмечает район из настроек, если он задан и ещё ничего не отмечено."""
        if not hasattr(self, "district_vars") or not self.district_vars:
            return
        if any(v.get() for v in self.district_vars.values()):
            return
        district = (self.settings or {}).get("default_district", "") or ""
        if district and district in self.district_vars:
            self.district_vars[district].set(True)
            self._refresh_objects()

    def _build_tab_persons(self, parent):
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", padx=8, pady=8)

        def add_person():
            dlg = PersonDialog19171(self) if self.procedure_code == "19.17.1" else PersonDialog143(self)
            self.wait_window(dlg)
            if dlg.result:
                self.persons.append(dlg.result)
                self._refresh_persons_list()

        def edit_person():
            sel = self.persons_listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            dlg = PersonDialog19171(self, self.persons[idx]) if self.procedure_code == "19.17.1" else PersonDialog143(self, self.persons[idx])
            self.wait_window(dlg)
            if dlg.result:
                self.persons[idx] = dlg.result
                self._refresh_persons_list()

        def del_person():
            sel = self.persons_listbox.curselection()
            if sel and messagebox.askyesno("Удалить", "Удалить выбранное лицо?"):
                del self.persons[sel[0]]
                self._refresh_persons_list()

        ttk.Button(toolbar, text="+ Добавить", command=add_person).pack(side="left", padx=4)
        ttk.Button(toolbar, text="✏ Редактировать", command=edit_person).pack(side="left", padx=4)
        ttk.Button(toolbar, text="🗑 Удалить", command=del_person).pack(side="left", padx=4)

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self.persons_listbox = tk.Listbox(list_frame, height=10, font=("", 12))
        self.persons_listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.persons_listbox.yview)
        scroll.pack(side="right", fill="y")
        self.persons_listbox.config(yscrollcommand=scroll.set)
        self._refresh_persons_list()

    def _refresh_persons_list(self):
        self.persons_listbox.delete(0, tk.END)
        if self.procedure_code == "19.17.1":
            for p in self.persons:
                self.persons_listbox.insert(tk.END, f"{p['last_name']} {p['first_name']} {p['middle_name']} — {p.get('position', '')}")
        else:
            for p in self.persons:
                self.persons_listbox.insert(tk.END, f"{p['last_name']} {p['first_name']} {p['middle_name']} ({p.get('birth_date', '')})")

    def _build_tab_vehicles(self, parent):
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", padx=8, pady=8)

        def add_vehicle():
            dlg = VehicleDialog(self)
            self.wait_window(dlg)
            if dlg.result:
                self.vehicles.append(dlg.result)
                self._refresh_vehicles_list()

        def edit_vehicle():
            sel = self.vehicles_listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            dlg = VehicleDialog(self, self.vehicles[idx])
            self.wait_window(dlg)
            if dlg.result:
                self.vehicles[idx] = dlg.result
                self._refresh_vehicles_list()

        def del_vehicle():
            sel = self.vehicles_listbox.curselection()
            if sel and messagebox.askyesno("Удалить", "Удалить выбранный автомобиль?"):
                del self.vehicles[sel[0]]
                self._refresh_vehicles_list()

        ttk.Button(toolbar, text="+ Добавить", command=add_vehicle).pack(side="left", padx=4)
        ttk.Button(toolbar, text="✏ Редактировать", command=edit_vehicle).pack(side="left", padx=4)
        ttk.Button(toolbar, text="🗑 Удалить", command=del_vehicle).pack(side="left", padx=4)

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self.vehicles_listbox = tk.Listbox(list_frame, height=10, font=("", 12))
        self.vehicles_listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.vehicles_listbox.yview)
        scroll.pack(side="right", fill="y")
        self.vehicles_listbox.config(yscrollcommand=scroll.set)
        self._refresh_vehicles_list()

    def _refresh_vehicles_list(self):
        self.vehicles_listbox.delete(0, tk.END)
        for v in self.vehicles:
            self.vehicles_listbox.insert(tk.END, f"{v['make']} — {v['number']}")

    def _build_tab_districts(self, parent):
        pad = {"padx": 6, "pady": 4}
        r = 0

        ttk.Label(parent, text="Районы (отметьте нужные):", font=("", 11, "bold")).grid(row=r, column=0, columnspan=2, sticky="w", **pad); r += 1
        self.district_vars = {}
        districts_frame = ttk.Frame(parent)
        districts_frame.grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1

        for i, d in enumerate(self.procedure.districts):
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(districts_frame, text=d, variable=var)
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=8, pady=2)
            self.district_vars[d] = var

        ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        ttk.Label(parent, text="Объекты:", font=("", 11, "bold")).grid(row=r, column=0, columnspan=2, sticky="w", **pad); r += 1

        # Для всех процедур: ПГРЭЗ + произвольный объект + справочник
        ttk.Checkbutton(parent, text='ГПНИУ "ПГРЭЗ"', variable=self.var_include_pgrez).grid(row=r, column=0, columnspan=2, sticky="w", **pad); r += 1
        ttk.Label(parent, text="Произвольный объект:").grid(row=r, column=0, sticky="w", **pad)
        e_custom_obj = ttk.Entry(parent, textvariable=self.var_custom_object, width=50)
        e_custom_obj.grid(row=r, column=1, columnspan=3, sticky="ew", **pad)
        bind_enter_as_tab(e_custom_obj)

        r += 1
        ttk.Label(parent, text="Справочник объектов (выберите по району):", font=("", 9)).grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
        self.objects_clb = CheckListbox(parent, height=6)
        self.objects_clb.grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        self._refresh_objects()

        for var in self.district_vars.values():
            var.trace_add("write", lambda *a: self._refresh_objects())

        # Район из настроек — отметить, если пользователь ещё ничего не выбрал.
        # Если в настройках задан подписант, его район уже отмечен
        # в _apply_signer_district, и здесь ничего не перезаписывается.
        self.after(60, self._apply_default_district)

    def _refresh_objects(self):
        if self.procedure_code == "19.17.1":
            return
        selected = self._selected_districts()
        ref = load_reference()
        filtered = filter_objects_by_districts(ref, selected)
        self.objects_clb.set_items([o["object"] for o in filtered])

    def _selected_districts(self) -> list:
        return [d for d, var in self.district_vars.items() if var.get()]

    def _build_tab_cargo(self, parent):
        pad = {"padx": 6, "pady": 4}
        ttk.Label(parent, text="Вид и количество имущества:", font=("", 11, "bold")).grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self.var_cargo, width=80).grid(row=0, column=1, columnspan=3, sticky="ew", padx=8, pady=4)

    def _build_buttons(self, parent):
        btns = ttk.Frame(parent)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        for i in range(5):
            btns.columnconfigure(i, weight=1)
        ttk.Button(btns, text="Сгенерировать документы", command=self.generate).grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(btns, text="Очистить форму", command=self.clear_form).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(btns, text="Куда сохранять…", command=self.choose_output).grid(row=0, column=2, sticky="ew", padx=2)
        ttk.Button(btns, text="Открыть папку", command=self.open_output).grid(row=0, column=3, sticky="ew", padx=2)
        ttk.Button(btns, text="⬅ Сменить процедуру", command=self.change_procedure).grid(row=0, column=4, sticky="ew", padx=2)

    def _collect_data(self) -> dict:
        data = {
            "last_name": self.var_last_name.get().strip(),
            "first_name": self.var_first_name.get().strip(),
            "middle_name": self.var_middle_name.get().strip(),
            "birth_date": self.var_birth_date.get().strip(),
            "id_number": self.var_id_number.get().strip(),
            "goal": self.var_goal.get().strip(),
            "date_from": self.var_date_from.get().strip(),
            "date_to": self.var_date_to.get().strip(),
            "issued_by": self.var_issued_by.get().strip(),
            "car_make": self.var_car_make.get().strip(),
            "car_number": self.var_car_number.get().strip(),
            "objects": self.objects_clb.get_checked() if self.procedure_code != "19.17.1" else [],
            "custom_object": self.var_custom_object.get().strip(),
            "include_pgrez": self.var_include_pgrez.get(),
            "cargo": self.var_cargo.get().strip(),
            "districts": self._selected_districts(),
            "persons": self.persons,
            "vehicles": self.vehicles,
        }
        if self.procedure_code == "19.17.1":
            data.update({
                "org_info": self.var_org_info.get().strip(),
                "org_short": self.var_org_short.get().strip(),
                "org_rep_last": self.var_org_rep_last.get().strip(),
                "org_rep_first": self.var_org_rep_first.get().strip(),
                "org_rep_middle": self.var_org_rep_middle.get().strip(),
            })
        return data

    @staticmethod
    def _check_period(date_from: str, date_to: str):
        """Проверяет срок: корректные даты, «по» не раньше «с», не больше 1 года.

        Возвращает текст ошибки или None.
        """
        d1 = DateMask.parse(date_from)
        d2 = DateMask.parse(date_to)
        if d1 is None or d2 is None:
            return "Даты должны быть в формате ДД.ММ.ГГГГ."
        if d2 < d1:
            return "Дата «По» не может быть раньше даты «С»."
        # 1 год: сравниваем с той же датой следующего года
        try:
            same_next = d1.replace(year=d1.year + 1)
        except ValueError:
            same_next = d1.replace(year=d1.year + 1, day=28)
        if d2 > same_next:
            return "Срок действия не может превышать 1 год."
        return None

    def _validate(self) -> bool:
        data = self._collect_data()
        if self.procedure_code == "19.17.1":
            if not data["org_info"] and not data["org_short"]:
                messagebox.showwarning(APP_NAME, "Укажите организацию.")
                return False
            if not data["persons"]:
                messagebox.showwarning(APP_NAME, "Добавьте хотя бы одно лицо.")
                return False
        else:
            if not data["last_name"] or not data["first_name"]:
                messagebox.showwarning(APP_NAME, "Укажите фамилию и имя заявителя.")
                return False
            if not data["districts"]:
                messagebox.showwarning(APP_NAME, "Отметьте хотя бы один район.")
                return False
        if not data["date_from"] or not data["date_to"]:
            messagebox.showwarning(APP_NAME, "Укажите срок действия (с/по).")
            return False
        err = self._check_period(data["date_from"], data["date_to"])
        if err:
            messagebox.showwarning(APP_NAME, err)
            return False
        return True

    def generate(self):
        if not self._validate():
            return
        data = self._collect_data()
        outdir = self.var_output.get().strip() or self._default_output()
        try:
            files = generate_all(data, outdir, self.procedure_code)
            msg = f"Готово! Создано документов: {len(files)}\n\n" + "\n".join(os.path.basename(f) for f in files)
            self.status_bar.config(text=f"Создано файлов: {len(files)}")
            if messagebox.askyesno(APP_NAME, msg + "\n\nОткрыть папку с документами?"):
                target = os.path.dirname(files[0]) if files else outdir
                os.makedirs(target, exist_ok=True)
                os.startfile(target)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Ошибка генерации:\n{ex}")

    def clear_form(self):
        for var in [self.var_last_name, self.var_first_name, self.var_middle_name,
                    self.var_birth_date, self.var_id_number, self.var_goal,
                    self.var_date_from, self.var_date_to, self.var_issued_by,
                    self.var_car_make, self.var_car_number, self.var_objects,
                    self.var_custom_object, self.var_cargo,
                    self.var_org_info, self.var_org_short,
                    self.var_org_rep_last, self.var_org_rep_first, self.var_org_rep_middle]:
            var.set("")
        self.var_include_pgrez.set(False)
        for var in self.district_vars.values():
            var.set(False)
        self._refresh_objects()
        self.persons.clear()
        self.vehicles.clear()
        self._refresh_persons_list()
        self._refresh_vehicles_list()
        self.status_bar.config(text="Форма очищена")

    def choose_output(self):
        d = filedialog.askdirectory(title="Выберите папку для сохранения документов")
        if d:
            self.var_output.set(d)

    def open_output(self):
        d = self.var_output.get()
        os.makedirs(d, exist_ok=True)
        os.startfile(d)


class PersonDialog143(tk.Toplevel):
    def __init__(self, parent, person=None):
        super().__init__(parent)
        self.title("Пассажир" if person else "Добавить пассажира")
        self.geometry("400x300")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        # Центрируем диалог на главном окне или экране
        self.update_idletasks()
        parent_app = parent
        while parent_app and not isinstance(parent_app, tk.Tk):
            parent_app = parent_app.master
        if parent_app and isinstance(parent_app, tk.Tk):
            x = parent_app.winfo_rootx() + max(0, (parent_app.winfo_width() - self.winfo_reqwidth()) // 2)
            y = parent_app.winfo_rooty() + max(0, (parent_app.winfo_height() - self.winfo_reqheight()) // 2)
            screen_w = parent_app.winfo_screenwidth()
            screen_h = parent_app.winfo_screenheight()
            x = max(10, min(x, screen_w - self.winfo_reqwidth() - 10))
            y = max(10, min(y, screen_h - self.winfo_reqheight() - 10))
            self.geometry(f"+{x}+{y}")
        self.result = None

        self.var_last = tk.StringVar(value=person.get("last_name", "") if person else "")
        self.var_first = tk.StringVar(value=person.get("first_name", "") if person else "")
        self.var_middle = tk.StringVar(value=person.get("middle_name", "") if person else "")
        self.var_birth = tk.StringVar(value=person.get("birth_date", "") if person else "")

        pad = {"padx": 8, "pady": 6}
        ttk.Label(self, text="Фамилия:").grid(row=0, column=0, sticky="w", **pad)
        e_last = ttk.Entry(self, textvariable=self.var_last, width=30)
        e_last.grid(row=0, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Имя:").grid(row=1, column=0, sticky="w", **pad)
        e_first = ttk.Entry(self, textvariable=self.var_first, width=30)
        e_first.grid(row=1, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Отчество:").grid(row=2, column=0, sticky="w", **pad)
        e_middle = ttk.Entry(self, textvariable=self.var_middle, width=30)
        e_middle.grid(row=2, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Дата рождения:").grid(row=3, column=0, sticky="w", **pad)
        e_pbirth = ttk.Entry(self, textvariable=self.var_birth, width=30)
        e_pbirth.grid(row=3, column=1, sticky="ew", **pad)
        attach_date_mask(e_pbirth, self.var_birth)

        # Ф.И.О.: первая буква заглавная; Enter = Tab
        for _e, _v in ((e_last, self.var_last), (e_first, self.var_first), (e_middle, self.var_middle)):
            _e.bind("<FocusOut>", lambda ev, v=_v: v.set(cap_word(v.get())), add="+")
        for _e in (e_last, e_first, e_middle, e_pbirth):
            bind_enter_as_tab(_e)
        self.after(50, lambda w=e_last: _safe_focus(w))

        btns = ttk.Frame(self)
        btns.grid(row=4, column=0, columnspan=2, pady=12)
        ttk.Button(btns, text="OK", command=self._ok).pack(side="left", padx=6)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=6)
        self.columnconfigure(1, weight=1)

    def _ok(self):
        if not self.var_last.get().strip() or not self.var_first.get().strip():
            messagebox.showwarning("Ошибка", "Фамилия и имя обязательны")
            return
        self.result = {
            "last_name": self.var_last.get().strip(),
            "first_name": self.var_first.get().strip(),
            "middle_name": self.var_middle.get().strip(),
            "birth_date": self.var_birth.get().strip(),
        }
        self.destroy()


class PersonDialog19171(tk.Toplevel):
    def __init__(self, parent, person=None):
        super().__init__(parent)
        self.title("Лицо" if person else "Добавить лицо")
        self.geometry("400x350")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        # Центрируем диалог на главном окне или экране
        self.update_idletasks()
        parent_app = parent
        while parent_app and not isinstance(parent_app, tk.Tk):
            parent_app = parent_app.master
        if parent_app and isinstance(parent_app, tk.Tk):
            x = parent_app.winfo_rootx() + max(0, (parent_app.winfo_width() - self.winfo_reqwidth()) // 2)
            y = parent_app.winfo_rooty() + max(0, (parent_app.winfo_height() - self.winfo_reqheight()) // 2)
            screen_w = parent_app.winfo_screenwidth()
            screen_h = parent_app.winfo_screenheight()
            x = max(10, min(x, screen_w - self.winfo_reqwidth() - 10))
            y = max(10, min(y, screen_h - self.winfo_reqheight() - 10))
            self.geometry(f"+{x}+{y}")
        self.result = None

        self.var_last = tk.StringVar(value=person.get("last_name", "") if person else "")
        self.var_first = tk.StringVar(value=person.get("first_name", "") if person else "")
        self.var_middle = tk.StringVar(value=person.get("middle_name", "") if person else "")
        self.var_pos = tk.StringVar(value=person.get("position", "") if person else "")

        pad = {"padx": 8, "pady": 6}
        ttk.Label(self, text="Фамилия:").grid(row=0, column=0, sticky="w", **pad)
        e_last = ttk.Entry(self, textvariable=self.var_last, width=30)
        e_last.grid(row=0, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Имя:").grid(row=1, column=0, sticky="w", **pad)
        e_first = ttk.Entry(self, textvariable=self.var_first, width=30)
        e_first.grid(row=1, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Отчество:").grid(row=2, column=0, sticky="w", **pad)
        e_middle = ttk.Entry(self, textvariable=self.var_middle, width=30)
        e_middle.grid(row=2, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Должность:").grid(row=3, column=0, sticky="w", **pad)
        e_pos = ttk.Entry(self, textvariable=self.var_pos, width=30)
        e_pos.grid(row=3, column=1, sticky="ew", **pad)

        # Ф.И.О. и Должность: первая буква заглавная; Enter = Tab
        for _e, _v in ((e_last, self.var_last), (e_first, self.var_first),
                       (e_middle, self.var_middle), (e_pos, self.var_pos)):
            _e.bind("<FocusOut>", lambda ev, v=_v: v.set(cap_word(v.get())), add="+")
        for _e in (e_last, e_first, e_middle, e_pos):
            bind_enter_as_tab(_e)
        self.after(50, lambda w=e_last: _safe_focus(w))

        btns = ttk.Frame(self)
        btns.grid(row=4, column=0, columnspan=2, pady=12)
        ttk.Button(btns, text="OK", command=self._ok).pack(side="left", padx=6)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=6)
        self.columnconfigure(1, weight=1)

    def _ok(self):
        if not self.var_last.get().strip() or not self.var_first.get().strip():
            messagebox.showwarning("Ошибка", "Фамилия и имя обязательны")
            return
        self.result = {
            "last_name": self.var_last.get().strip(),
            "first_name": self.var_first.get().strip(),
            "middle_name": self.var_middle.get().strip(),
            "position": self.var_pos.get().strip(),
        }
        self.destroy()


class VehicleDialog(tk.Toplevel):
    def __init__(self, parent, vehicle=None):
        super().__init__(parent)
        self.title("Автомобиль" if vehicle else "Добавить автомобиль")
        self.geometry("400x180")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        # Центрируем диалог на главном окне или экране
        self.update_idletasks()
        parent_app = parent
        while parent_app and not isinstance(parent_app, tk.Tk):
            parent_app = parent_app.master
        if parent_app and isinstance(parent_app, tk.Tk):
            x = parent_app.winfo_rootx() + max(0, (parent_app.winfo_width() - self.winfo_reqwidth()) // 2)
            y = parent_app.winfo_rooty() + max(0, (parent_app.winfo_height() - self.winfo_reqheight()) // 2)
            screen_w = parent_app.winfo_screenwidth()
            screen_h = parent_app.winfo_screenheight()
            x = max(10, min(x, screen_w - self.winfo_reqwidth() - 10))
            y = max(10, min(y, screen_h - self.winfo_reqheight() - 10))
            self.geometry(f"+{x}+{y}")
        self.result = None

        self.var_make = tk.StringVar(value=vehicle.get("make", "") if vehicle else "")
        self.var_number = tk.StringVar(value=vehicle.get("number", "") if vehicle else "")

        pad = {"padx": 8, "pady": 6}
        ttk.Label(self, text="Марка-модель:").grid(row=0, column=0, sticky="w", **pad)
        e_make = ttk.Entry(self, textvariable=self.var_make, width=30)
        e_make.grid(row=0, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Гос. номер:").grid(row=1, column=0, sticky="w", **pad)
        e_number = ttk.Entry(self, textvariable=self.var_number, width=30)
        e_number.grid(row=1, column=1, sticky="ew", **pad)

        # Марка-модель: первая буква заглавная; Гос. номер: полностью заглавными
        e_make.bind("<FocusOut>", lambda ev: self.var_make.set(cap_first(self.var_make.get())), add="+")
        e_number.bind("<FocusOut>", lambda ev: self.var_number.set(cap_id(self.var_number.get())), add="+")
        for _e in (e_make, e_number):
            bind_enter_as_tab(_e)
        self.after(50, lambda w=e_make: _safe_focus(w))

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, columnspan=2, pady=12)
        ttk.Button(btns, text="OK", command=self._ok).pack(side="left", padx=6)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=6)
        self.columnconfigure(1, weight=1)

    def _ok(self):
        if not self.var_make.get().strip() or not self.var_number.get().strip():
            messagebox.showwarning("Ошибка", "Марка и гос. номер обязательны")
            return
        self.result = {
            "make": self.var_make.get().strip(),
            "number": self.var_number.get().strip(),
        }
        self.destroy()


class SettingsDialog(tk.Toplevel):
    """Окно настроек: подписант по умолчанию и связанный с ним район."""

    def __init__(self, parent, settings, get_proc):
        super().__init__(parent)
        self.title("Настройки")
        self.geometry("520x300")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.update_idletasks()
        parent_app = parent
        while parent_app and not isinstance(parent_app, tk.Tk):
            parent_app = parent_app.master
        if parent_app and isinstance(parent_app, tk.Tk):
            x = parent_app.winfo_rootx() + max(0, (parent_app.winfo_width() - self.winfo_reqwidth()) // 2)
            y = parent_app.winfo_rooty() + max(0, (parent_app.winfo_height() - self.winfo_reqheight()) // 2)
            self.geometry("+" + str(max(10, x)) + "+" + str(max(10, y)))

        pad = {"padx": 10, "pady": 8}
        ttk.Label(self, text="Кому на подписание по умолчанию:", font=("", 11, "bold")).grid(
            row=0, column=0, sticky="w", **pad)
        self.var_signer = tk.StringVar(value=(settings or {}).get("default_signer", "") or "")
        signers = list(get_proc("14.3").signers)
        cb = ttk.Combobox(self, textvariable=self.var_signer, values=[""] + signers,
                          width=50, state="readonly")
        cb.grid(row=0, column=1, sticky="ew", **pad)

        ttk.Label(self, text="Район по умолчанию:", font=("", 11, "bold")).grid(
            row=1, column=0, sticky="w", **pad)
        self.var_district = tk.StringVar(value=(settings or {}).get("default_district", "") or "")
        districts = list(get_proc("14.3").districts)
        self.cb_district = ttk.Combobox(self, textvariable=self.var_district,
                                        values=[""] + districts, width=50, state="readonly")
        self.cb_district.grid(row=1, column=1, sticky="ew", **pad)

        ttk.Label(
            self,
            text=("Район подставляется автоматически по выбранному подписанту.\n"
                  "Здесь можно задать район вручную, если подписант его не имеет."),
            foreground="gray", justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8))

        # Смена подписанта -> предложить его «родной» район
        cb.bind("<<ComboboxSelected>>", self._on_signer_change)

        btns = ttk.Frame(self)
        btns.grid(row=3, column=0, columnspan=2, pady=12)
        ttk.Button(btns, text="Сохранить", command=self._ok).pack(side="left", padx=6)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=6)
        self.columnconfigure(1, weight=1)

    def _on_signer_change(self, event=None):
        d = SIGNER_DISTRICT.get(self.var_signer.get())
        if d:
            self.var_district.set(d)

    def _ok(self):
        self.result = {
            "default_signer": self.var_signer.get().strip(),
            "default_district": self.var_district.get().strip(),
        }
        self.destroy()


def main():
    app = PermitApp()
    app.mainloop()


if __name__ == "__main__":
    main()
