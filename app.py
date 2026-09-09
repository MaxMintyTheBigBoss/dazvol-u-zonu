# -*- coding: utf-8 -*-
"""
Единое приложение «Генератор пропусков» — выбор процедуры + генерация.
Объединяет 14.3, 14.5, 19.17.1 в одно окно с выбором процедуры при запуске.
"""
import os
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
APP_VERSION = "1.0.0"
APP_EXE_NAME = f"dazvol_u_zonu_ver.{APP_VERSION}.exe"
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

    def _on_type(self, event):
        """Автоматическая маска ДД.ММ.ГГГГ."""
        text = self.var.get()
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) > 8:
            digits = digits[:8]
        formatted = ""
        if len(digits) >= 2:
            formatted = digits[:2] + "."
        if len(digits) >= 4:
            formatted += digits[2:4] + "."
        if len(digits) > 4:
            formatted += digits[4:]
        if formatted != text:
            cursor_pos = self.entry.index(tk.INSERT)
            self.var.set(formatted)
            new_pos = min(cursor_pos, len(formatted))
            self.entry.icursor(new_pos)

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
        ttk.Label(self, text="Выбор процедуры", font=("", 16, "bold")).pack(pady=(0, 8))

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
                font=("", 18, "bold"),
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
        
        # Ensure window is shown
        self.deiconify()
        self.update_idletasks()
        
        self.show_menu()

    # ------------------------------------------------------------------
    # Главное меню
    # ------------------------------------------------------------------
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
            dlg_upd = UpdateDialog(self, APP_VERSION, APP_EXE_NAME)
            self.wait_window(dlg_upd)
        except Exception as e:
            messagebox.showerror("Обновления", f"Ошибка: {e}", parent=self)

    def action_about(self):
        self._show_about()

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
            f"Версия {APP_VERSION}\n"
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
            style.configure(".", font=("", 11))
            style.configure("TButton", font=("", 11, "bold"))
            style.map("TButton", background=[("active", BTN_ACTIVE), ("!active", BTN_BG)])

            header = ttk.Frame(parent)
            header.pack(fill="x", padx=10, pady=8)
            ttk.Label(header, text=self.procedure.name, font=("", 14, "bold"),
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

    def _build_tab_applicant(self, parent):
        pad = {"padx": 6, "pady": 4}
        r = 0

        if self.procedure_code == "19.17.1":
            # Организация (краткое наименование) — одна строка
            ttk.Label(parent, text="Организация (краткое наименование):").grid(row=r, column=0, sticky="w", **pad)
            ttk.Entry(parent, textvariable=self.var_org_info, width=60).grid(row=r, column=1, columnspan=3, sticky="ew", **pad); r += 1
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
            ttk.Entry(parent, textvariable=self.var_last_name, width=30).grid(row=r, column=1, sticky="ew", **pad)
            ttk.Label(parent, text="Имя:").grid(row=r, column=2, sticky="w", **pad)
            ttk.Entry(parent, textvariable=self.var_first_name, width=30).grid(row=r, column=3, sticky="ew", **pad); r += 1
            ttk.Label(parent, text="Отчество:").grid(row=r, column=0, sticky="w", **pad)
            ttk.Entry(parent, textvariable=self.var_middle_name, width=30).grid(row=r, column=1, sticky="ew", **pad)
            ttk.Label(parent, text="Дата рождения:").grid(row=r, column=2, sticky="w", **pad)
            DateEntryWithCalendar(parent, "", self.var_birth_date).grid(row=r, column=3, sticky="ew", **pad); r += 1
            ttk.Label(parent, text="Личный номер:").grid(row=r, column=0, sticky="w", **pad)
            ttk.Entry(parent, textvariable=self.var_id_number, width=30).grid(row=r, column=1, sticky="ew", **pad); r += 1

        ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        ttk.Label(parent, text="Цель въезда:", font=("", 11, "bold")).grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
        if self.procedure.goal_fixed:
            self.var_goal.set(self.procedure.goal_fixed)
            ttk.Label(parent, text=self.procedure.goal_fixed, foreground="gray").grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
        elif self.procedure.goal_options:
            ttk.Combobox(parent, textvariable=self.var_goal, values=self.procedure.goal_options, width=55).grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        else:
            ttk.Entry(parent, textvariable=self.var_goal, width=60).grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1

        ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        ttk.Label(parent, text="Срок действия:", font=("", 11, "bold")).grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
        ttk.Label(parent, text="С:").grid(row=r, column=0, sticky="w", **pad)
        DateEntryWithCalendar(parent, "", self.var_date_from).grid(row=r, column=1, sticky="ew", **pad)
        ttk.Label(parent, text="По:").grid(row=r, column=2, sticky="w", **pad)
        DateEntryWithCalendar(parent, "", self.var_date_to).grid(row=r, column=3, sticky="ew", **pad); r += 1

        ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        ttk.Label(parent, text="Кому на подписание:", font=("", 11, "bold")).grid(row=r, column=0, sticky="w", **pad)
        self.var_issued_by = tk.StringVar(value=self.procedure.signers[0] if self.procedure.signers else "")
        ttk.Combobox(parent, textvariable=self.var_issued_by, values=self.procedure.signers, width=55, state="readonly").grid(row=r, column=1, columnspan=3, sticky="ew", **pad)

        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

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
        ttk.Entry(parent, textvariable=self.var_custom_object, width=50).grid(row=r, column=1, columnspan=3, sticky="ew", **pad)

        r += 1
        ttk.Label(parent, text="Справочник объектов (выберите по району):", font=("", 9)).grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
        self.objects_clb = CheckListbox(parent, height=6)
        self.objects_clb.grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        self._refresh_objects()

        for var in self.district_vars.values():
            var.trace_add("write", lambda *a: self._refresh_objects())

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
        ttk.Entry(self, textvariable=self.var_last, width=30).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Имя:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.var_first, width=30).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Отчество:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.var_middle, width=30).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Дата рождения:").grid(row=3, column=0, sticky="w", **pad)
        DateEntryWithCalendar(self, "", self.var_birth).grid(row=3, column=1, sticky="ew", **pad)

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
        ttk.Entry(self, textvariable=self.var_last, width=30).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Имя:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.var_first, width=30).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Отчество:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.var_middle, width=30).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Должность:").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.var_pos, width=30).grid(row=3, column=1, sticky="ew", **pad)

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
        ttk.Entry(self, textvariable=self.var_make, width=30).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Гос. номер:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.var_number, width=30).grid(row=1, column=1, sticky="ew", **pad)

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


def main():
    app = PermitApp()
    app.mainloop()


if __name__ == "__main__":
    main()
