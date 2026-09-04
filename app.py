# -*- coding: utf-8 -*-
"""
Единое приложение «Генератор пропусков» — выбор процедуры + генерация.
Объединяет 14.3, 14.5, 19.17.1 в одно окно с выбором процедуры при запуске.
"""
import os
import sys
# runtime_hook rthook_tcl.py настраивает TCL_LIBRARY/TK_LIBRARY ДО импорта tkinter
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
APP_VERSION = "0.0.6"
BG_COLOR = "#E6EBE0"
BTN_BG = "#CAD4CC"
BTN_ACTIVE = "#B3C3B8"

# Цвета для процедур
PROC_COLORS = {
    "14.3": "#009D92",  # бирюзовый
    "14.5": "#FDD9B5",  # песочный
    "19.17.1": "#E6EBE0",  # серо-голубой
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

    def bind_wheel(self, widget):
        """Привязка колеса мыши только при наведении на canvas."""
        def on_enter(e):
            widget.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        def on_leave(e):
            widget.unbind_all("<MouseWheel>")
        self.canvas.bind("<Enter>", on_enter)
        self.canvas.bind("<Leave>", on_leave)


class DateEntryWithCalendar(ttk.Frame):
    """Поле даты с маской ДД.ММ.ГГГГ и кнопкой календаря."""

    def __init__(self, master, label: str, var: tk.StringVar, width=18, **kw):
        super().__init__(master, **kw)
        self.var = var
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
            # корректируем позицию курсора
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
        cal = _TkCalendar(top, date_pattern="dd.mm.yyyy", firstweekday="monday")
        cal.pack(padx=10, pady=10)
        def on_select():
            self.var.set(cal.get_date())
            top.destroy()
        ttk.Button(top, text="Выбрать", command=on_select).pack(pady=5)


class ProcedureSelectDialog(tk.Toplevel):
    """Главное меню: выбор процедуры + управление БД и обновлениями."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title(APP_NAME)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.selected_proc = None
        self.selected_action = None  # 'export_db', 'import_db', 'check_updates'

        # Главный контейнер
        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)

        # === Заголовок ===
        ttk.Label(
            main, text="Выбор процедуры", font=("", 16, "bold")
        ).pack(pady=(0, 8))

        # === Кнопки выбора процедуры (3 большие) ===
        procedures_list = [p for p in list_procedures()]
        procedures_list.sort(key=lambda p: p.code)

        proc_frame = ttk.Frame(main)
        proc_frame.pack(fill="both", expand=True, pady=8)

        for proc in procedures_list:
            color = PROC_COLORS.get(proc.code, "#999")
            fg = "white" if color not in ("#E6EBE0", "#FDD9B5", "#D4FCEE") else "black"
            btn = tk.Button(
                proc_frame,
                text=proc.code,
                font=("", 18, "bold"),
                bg=color,
                fg=fg,
                activebackground=color,
                activeforeground=fg,
                relief="flat",
                cursor="hand2",
                height=2,
                command=lambda p=proc.code: self._select(p),
            )
            btn.pack(fill="x", expand=True, padx=4, pady=4)

        # === Разделитель ===
        ttk.Separator(main, orient="horizontal").pack(fill="x", pady=10)

        # === Кнопки управления БД и обновлениями ===
        actions_frame = ttk.Frame(main)
        actions_frame.pack(fill="x", pady=4)

        ttk.Button(
            actions_frame, text="📤 Выгрузить БД",
            command=self._action_export
        ).pack(side="left", fill="x", expand=True, padx=2)

        ttk.Button(
            actions_frame, text="📥 Загрузить БД",
            command=self._action_import
        ).pack(side="left", fill="x", expand=True, padx=2)

        ttk.Button(
            actions_frame, text="🔄 Обновления",
            command=self._action_update
        ).pack(side="left", fill="x", expand=True, padx=2)

        # === Выход ===
        ttk.Button(
            main, text="Выход", command=self._cancel
        ).pack(fill="x", pady=(8, 0))

        # Центрируем окно относительно родительского
        self._center_on_parent(parent)

    def _center_on_parent(self, parent):
        """Центрирует окно относительно parent или экрана."""
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        if parent and parent.winfo_viewable():
            # Относительно parent
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
        else:
            # По центру экрана
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _select(self, proc_code: str):
        self.selected_proc = proc_code
        self.selected_action = "procedure"
        self.destroy()

    def _action_export(self):
        self.selected_action = "export_db"
        self.destroy()

    def _action_import(self):
        self.selected_action = "import_db"
        self.destroy()

    def _action_update(self):
        self.selected_action = "check_updates"
        self.destroy()

    def _cancel(self):
        self.selected_proc = None
        self.selected_action = "cancel"
        self.destroy()


class PermitApp(tk.Tk):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("900x750")
        self.minsize(850, 700)
        self.configure(bg=BG_COLOR)

        # Сначала — выбор процедуры
        self._choose_procedure()
        if not hasattr(self, 'procedure_code') or not self.procedure_code:
            self.destroy()
            return

        self.procedure = get_procedure(self.procedure_code)
        self.configure(bg=PROC_COLORS.get(self.procedure_code, BG_COLOR))

        # Переменные формы
        self._init_variables()
        self._build_ui()
        self._refresh_db_lists()

    def _choose_procedure(self):
        """Модальный диалог: выбор процедуры / действие / выход."""
        while True:
            dlg = ProcedureSelectDialog(self)
            self.wait_window(dlg)

            action = getattr(dlg, 'selected_action', None)
            code = dlg.selected_proc

            if action == "cancel" or code is None:
                # Выход
                self.procedure_code = None
                return

            if action == "export_db":
                export_db_dialog(self, get_db_path(), "permits_export_XXXX.json")
                continue  # Показываем диалог снова

            if action == "import_db":
                self._import_db()
                continue

            if action == "check_updates":
                dlg_upd = UpdateDialog(self, APP_VERSION, "dazvol_u_zonu.exe")
                self.wait_window(dlg_upd)
                continue

            if action == "procedure" and code:
                self.procedure_code = code
                return

            # На всякий случай
            self.procedure_code = code
            return

    def _import_db(self):
        """Импорт БД из JSON файла."""
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
            messagebox.showinfo(
                "Импорт БД",
                f"Импортировано записей: {imported}\n\n"
                f"Файл: {path}",
            )
        except Exception as e:
            messagebox.showerror("Ошибка импорта БД", f"Не удалось импортировать:\n{e}")

    def _init_variables(self):
        """Инициализация переменных формы в зависимости от процедуры."""
        p = self.procedure

        # Общие
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

        # Для 19.17.1
        self.var_org_info = tk.StringVar()
        self.var_org_short = tk.StringVar()
        self.var_org_rep_last = tk.StringVar()
        self.var_org_rep_first = tk.StringVar()
        self.var_org_rep_middle = tk.StringVar()

        # Списки
        self.persons = []  # список словарей
        self.vehicles = []  # список словарей

        # DB combobox
        self.db_combo = None

    def _default_output(self):
        base = Path(__file__).parent.parent if not getattr(sys, 'frozen', False) else Path(os.path.dirname(os.path.abspath(sys.argv[0])))
        return str(base / "output")

    def _build_ui(self):
        # Стиль
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=PROC_COLORS.get(self.procedure_code, BG_COLOR))
        style.configure("TLabel", background=PROC_COLORS.get(self.procedure_code, BG_COLOR))
        style.configure("TCheckbutton", background=PROC_COLORS.get(self.procedure_code, BG_COLOR))
        style.configure("TNotebook", background=PROC_COLORS.get(self.procedure_code, BG_COLOR))
        style.configure("TNotebook.Tab", padding=(12, 6), font=("", 11, "bold"))
        style.map("TNotebook.Tab", background=[("selected", BTN_ACTIVE)], foreground=[("selected", "black")])
        style.configure(".", font=("", 11))
        style.configure("TButton", font=("", 11, "bold"))
        style.configure("TLabel", font=("", 11))
        style.configure("TEntry", font=("", 11))
        style.configure("TCombobox", font=("", 11))
        style.configure("TCheckbutton", font=("", 11))
        style.map("TButton", background=[("active", BTN_ACTIVE), ("!active", BTN_BG)])

        # Заголовок с названием процедуры
        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=8)
        ttk.Label(header, text=self.procedure.name, font=("", 14, "bold"),
                  foreground=PROC_COLORS.get(self.procedure_code, "black")).pack(side="left", padx=10)
        ttk.Button(header, text="← Сменить процедуру", command=self._change_procedure).pack(side="right", padx=10)

        # Notebook с вкладками
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)

        # Вкладка 1: Заявитель / Организация
        tab1 = ttk.Frame(self.nb)
        self.nb.add(tab1, text="1. Заявитель / Организация")
        self._build_tab_applicant(tab1)

        # Вкладка 2: Пассажиры / Лица (если предусмотрено)
        if self.procedure.has_individual_permits:
            tab2 = ttk.Frame(self.nb)
            self.nb.add(tab2, text="2. Лица / Пассажиры")
            self._build_tab_persons(tab2)

        # Вкладка 3: Автомобили
        if self.procedure.has_transport_permits:
            tab3 = ttk.Frame(self.nb)
            self.nb.add(tab3, text="3. Автомобили")
            self._build_tab_vehicles(tab3)

        # Вкладка 4: Районы, объекты, подписант
        tab4 = ttk.Frame(self.nb)
        self.nb.add(tab4, text="4. Районы / Объекты / Подписант")
        self._build_tab_districts(tab4)

        # Вкладка 5: Груз (только 14.5)
        if self.procedure.has_cargo_permit:
            tab5 = ttk.Frame(self.nb)
            self.nb.add(tab5, text="5. Груз")
            self._build_tab_cargo(tab5)

        # Вкладка О программе
        tab_about = ttk.Frame(self.nb)
        self.nb.add(tab_about, text="О программе")
        self._build_about_tab(tab_about)

        # Кнопки внизу (всегда видны)
        self._build_buttons()

        # Статус-бар
        self.status_bar = ttk.Label(self, text="Готово", relief="sunken", anchor="w")
        self.status_bar.pack(fill="x", padx=8, pady=(0, 8))

    def _change_procedure(self):
        if messagebox.askyesno("Смена процедуры", "Текущие данные формы будут потеряны. Продолжить?"):
            self.destroy()
            # Перезапуск — проще через пересоздание
            import subprocess
            subprocess.Popen([sys.executable] + sys.argv)
            sys.exit(0)

    def _build_tab_applicant(self, parent):
        pad = {"padx": 6, "pady": 4}
        r = 0

        p = self.procedure

        if self.procedure_code == "19.17.1":
            # Организация
            ttk.Label(parent, text="Организация (полное наименование):").grid(row=r, column=0, sticky="w", **pad)
            ttk.Entry(parent, textvariable=self.var_org_info, width=60).grid(row=r, column=1, columnspan=3, sticky="ew", **pad)
            r += 1
            ttk.Label(parent, text="Организация (краткое):").grid(row=r, column=0, sticky="w", **pad)
            ttk.Entry(parent, textvariable=self.var_org_short, width=60).grid(row=r, column=1, columnspan=3, sticky="ew", **pad)
            r += 1
            # Представитель организации
            ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
            ttk.Label(parent, text="Представитель организации:", font=("", 11, "bold")).grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
            ttk.Label(parent, text="Фамилия:").grid(row=r, column=0, sticky="w", **pad)
            ttk.Entry(parent, textvariable=self.var_org_rep_last, width=30).grid(row=r, column=1, sticky="ew", **pad)
            ttk.Label(parent, text="Имя:").grid(row=r, column=2, sticky="w", **pad)
            ttk.Entry(parent, textvariable=self.var_org_rep_first, width=30).grid(row=r, column=3, sticky="ew", **pad); r += 1
            ttk.Label(parent, text="Отчество:").grid(row=r, column=0, sticky="w", **pad)
            ttk.Entry(parent, textvariable=self.var_org_rep_middle, width=30).grid(row=r, column=1, sticky="ew", **pad); r += 1
        else:
            # ФИО заявителя
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

        # Цель въезда
        ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        ttk.Label(parent, text="Цель въезда:", font=("", 11, "bold")).grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
        if self.procedure.goal_fixed:
            self.var_goal.set(self.procedure.goal_fixed)
            ttk.Label(parent, text=self.procedure.goal_fixed, foreground="gray").grid(row=r, column=0, columnspan=4, sticky="w", **pad)
            r += 1
        elif self.procedure.goal_options:
            ttk.Combobox(parent, textvariable=self.var_goal, values=self.procedure.goal_options, width=55).grid(row=r, column=0, columnspan=4, sticky="ew", **pad)
            r += 1
        else:
            ttk.Entry(parent, textvariable=self.var_goal, width=60).grid(row=r, column=0, columnspan=4, sticky="ew", **pad)
            r += 1

        # Срок действия
        ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        ttk.Label(parent, text="Срок действия:", font=("", 11, "bold")).grid(row=r, column=0, columnspan=4, sticky="w", **pad); r += 1
        ttk.Label(parent, text="С:").grid(row=r, column=0, sticky="w", **pad)
        DateEntryWithCalendar(parent, "", self.var_date_from).grid(row=r, column=1, sticky="ew", **pad)
        ttk.Label(parent, text="По:").grid(row=r, column=2, sticky="w", **pad)
        DateEntryWithCalendar(parent, "", self.var_date_to).grid(row=r, column=3, sticky="ew", **pad); r += 1

        # Кому на подписание
        ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        ttk.Label(parent, text="Кому на подписание:", font=("", 11, "bold")).grid(row=r, column=0, sticky="w", **pad)
        self.var_issued_by = tk.StringVar(value=self.procedure.signers[0] if self.procedure.signers else "")
        self.db_combo = ttk.Combobox(parent, textvariable=self.var_issued_by, values=self.procedure.signers, width=55, state="readonly")
        self.db_combo.grid(row=r, column=1, columnspan=3, sticky="ew", **pad)
        r += 1

        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

    def _build_tab_persons(self, parent):
        """Вкладка: список лиц (пассажиры для 14.3/14.5, лица для 19.17.1)."""
        pad = {"padx": 6, "pady": 4}
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", padx=8, pady=8)

        def add_person():
            if self.procedure_code == "19.17.1":
                dlg = PersonDialog19171(self)
                self.wait_window(dlg)
                if dlg.result:
                    self.persons.append(dlg.result)
                    self._refresh_persons_list()
            else:
                dlg = PersonDialog143(self)
                self.wait_window(dlg)
                if dlg.result:
                    self.persons.append(dlg.result)
                    self._refresh_persons_list()

        def edit_person():
            sel = self.persons_listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            if self.procedure_code == "19.17.1":
                dlg = PersonDialog19171(self, self.persons[idx])
            else:
                dlg = PersonDialog143(self, self.persons[idx])
            self.wait_window(dlg)
            if dlg.result:
                self.persons[idx] = dlg.result
                self._refresh_persons_list()

        def del_person():
            sel = self.persons_listbox.curselection()
            if not sel:
                return
            if messagebox.askyesno("Удалить", "Удалить выбранное лицо?"):
                del self.persons[sel[0]]
                self._refresh_persons_list()

        ttk.Button(toolbar, text="+ Добавить", command=add_person).pack(side="left", padx=4)
        ttk.Button(toolbar, text="✏ Редактировать", command=edit_person).pack(side="left", padx=4)
        ttk.Button(toolbar, text="🗑 Удалить", command=del_person).pack(side="left", padx=4)

        # Список
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
                pos = p.get("position", "")
                self.persons_listbox.insert(tk.END, f"{p['last_name']} {p['first_name']} {p['middle_name']} — {pos}")
        else:
            for p in self.persons:
                bd = p.get("birth_date", "")
                self.persons_listbox.insert(tk.END, f"{p['last_name']} {p['first_name']} {p['middle_name']} ({bd})")

    def _build_tab_vehicles(self, parent):
        """Вкладка: список автомобилей."""
        pad = {"padx": 6, "pady": 4}
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
            if not sel:
                return
            if messagebox.askyesno("Удалить", "Удалить выбранный автомобиль?"):
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

        # Районы
        ttk.Label(parent, text="Районы (отметьте нужные):", font=("", 11, "bold")).grid(row=r, column=0, columnspan=2, sticky="w", **pad); r += 1
        self.district_vars = {}
        districts_frame = ttk.Frame(parent)
        districts_frame.grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        # Вывод в 2 колонки
        for i, d in enumerate(self.procedure.districts):
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(districts_frame, text=d, variable=var)
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=8, pady=2)
            self.district_vars[d] = var

        # Объекты / PGREZ / Произвольный объект
        ttk.Separator(parent, orient="horizontal").grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
        ttk.Label(parent, text="Объекты (кладбища):", font=("", 11, "bold")).grid(row=r, column=0, columnspan=2, sticky="w", **pad); r += 1

        # Чекбокс PGREZ для 19.17.1
        if self.procedure_code == "19.17.1":
            ttk.Checkbutton(parent, text='ГПНИУ "ПГРЭЗ"', variable=self.var_include_pgrez).grid(row=r, column=0, columnspan=2, sticky="w", **pad); r += 1
            ttk.Label(parent, text="Произвольный объект:").grid(row=r, column=0, sticky="w", **pad)
            ttk.Entry(parent, textvariable=self.var_custom_object, width=50).grid(row=r, column=1, columnspan=3, sticky="ew", **pad); r += 1
        else:
            # Для 14.3/14.5 — автозаполнение из справочника по выбранным районам
            self.objects_clb = CheckListbox(parent, height=8)
            self.objects_clb.grid(row=r, column=0, columnspan=4, sticky="ew", **pad); r += 1
            self._refresh_objects()

        # Обновление объектов при смене районов
        for var in self.district_vars.values():
            var.trace_add("write", lambda *a: self._refresh_objects())

    def _refresh_objects(self):
        """Обновляет список объектов (кладбищ) в зависимости от выбранных районов."""
        if self.procedure_code == "19.17.1":
            return
        selected = self._selected_districts()
        ref = load_reference()
        filtered = filter_objects_by_districts(ref, selected)
        self.objects_clb.set_items([o["object"] for o in filtered])

    def _selected_districts(self) -> list:
        return [d for d, var in self.district_vars.items() if var.get()]

    def _build_tab_cargo(self, parent):
        """Вкладка груз (только 14.5)."""
        pad = {"padx": 6, "pady": 4}
        ttk.Label(parent, text="Вид и количество имущества:", font=("", 11, "bold")).grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self.var_cargo, width=80).grid(row=0, column=1, columnspan=3, sticky="ew", padx=8, pady=4)

    def _build_buttons(self):
        """Нижняя панель кнопок — всегда видна."""
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        for i in range(6):
            btns.columnconfigure(i, weight=1)
        ttk.Button(btns, text="Сгенерировать документы", command=self.generate).grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(btns, text="Очистить форму", command=self.clear_form).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(btns, text="Куда сохранять…", command=self.choose_output).grid(row=0, column=2, sticky="ew", padx=2)
        ttk.Button(btns, text="Открыть папку", command=self.open_output).grid(row=0, column=3, sticky="ew", padx=2)
        ttk.Button(btns, text="Выгрузить БД", command=self.export_db).grid(row=0, column=4, sticky="ew", padx=2)
        ttk.Button(btns, text="Обновления…", command=self.check_updates).grid(row=0, column=5, sticky="ew", padx=2)

    def _build_about_tab(self, parent):
        txt = (
            f"{APP_NAME}\n"
            f"Версия {APP_VERSION}\n\n"
            "Создатель: Соломейчук Алексей\n"
            "Creator: Salamiaichuk Aliaksei\n\n"
            "Email: al.vl.solo@yandex.by\n\n"
            "© 2025 Соломейчук Алексей / Salamiaichuk Aliaksei\n\n"
            "Все права защищены.\n\n"
            "Единое приложение для генерации пропусков по процедурам:\n"
            "  • Пункт 14.3 — Благоустройство могил\n"
            "  • Пункт 14.5 — Вывоз имущества\n"
            "  • Пункт 19.17.1 — Мониторинг и работы\n\n"
            "Возможности:\n"
            "  • Единое окно с выбором процедуры\n"
            "  • Маска дат ДД.ММ.ГГГГ + календарь\n"
            "  • Поиск в базе (ФИО/Организация) с автодополнением\n"
            "  • Выгрузка БД в JSON/CSV/Excel\n"
            "  • Обновление через GitHub или локальный .zip"
        )
        lbl = ttk.Label(parent, text=txt, justify="left", anchor="nw", wraplength=800)
        lbl.pack(fill="both", expand=True, padx=16, pady=16)

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------
    def _collect_data(self) -> dict:
        """Собирает данные формы в словарь для генерации."""
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
            "objects": self.var_objects.get().strip() if self.procedure_code != "19.17.1" else "",
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
            if not data["vehicles"] and self.procedure.has_transport_permits:
                messagebox.showwarning(APP_NAME, "Добавьте хотя бы один автомобиль.")
                return False
        else:
            if not data["last_name"] or not data["first_name"]:
                messagebox.showwarning(APP_NAME, "Укажите фамилию и имя заявителя.")
                return False
            if self.procedure_code == "14.3" and data["goal"] == "свой вариант" and not data["goal"].strip():
                messagebox.showwarning(APP_NAME, "Укажите цель въезда.")
                return False
            if not data["districts"]:
                messagebox.showwarning(APP_NAME, "Отметьте хотя бы один район.")
                return False
        if not data["date_from"] or not data["date_to"]:
            messagebox.showwarning(APP_NAME, "Укажите срок действия (с/по).")
            return False
        if self.procedure.has_transport_permits and (data["car_make"] or data["car_number"]) and not data["vehicles"]:
            if not data["car_make"] and not data["car_number"]:
                pass  # просто не будет транспортного пропуска
        return True

    def generate(self):
        if not self._validate():
            return
        data = self._collect_data()
        outdir = self.var_output.get().strip() or self._default_output()
        try:
            files = generate_all(data, outdir, self.procedure_code)
            msg = "Готово! Создано документов: %d\n\n%s" % (len(files), "\n".join(os.path.basename(f) for f in files))
            self.status_bar.config(text="Создано файлов: %d" % len(files))
            if messagebox.askyesno(APP_NAME, msg + "\n\nОткрыть папку с документами?"):
                os.makedirs(os.path.dirname(files[0]), exist_ok=True)
                os.startfile(os.path.dirname(files[0]))
        except Exception as ex:
            messagebox.showerror(APP_NAME, "Ошибка генерации:\n%s" % ex)

    def clear_form(self):
        """Полная очистка формы."""
        for var in [self.var_last_name, self.var_first_name, self.var_middle_name,
                    self.var_birth_date, self.var_id_number, self.var_goal,
                    self.var_date_from, self.var_date_to, self.var_issued_by,
                    self.var_car_make, self.var_car_number, self.var_objects,
                    self.var_custom_object, self.var_cargo,
                    self.var_org_info, self.var_org_short,
                    self.var_org_rep_last, self.var_org_rep_first, self.var_org_rep_middle]:
            var.set("")
        self.var_include_pgrez.set(False)
        self.var_goal.set("")
        self.var_date_from.set("")
        self.var_date_to.set("")
        if self.procedure_code != "19.17.1" and self.procedure.goal_options:
            self.var_goal.set(self.procedure.goal_options[0])
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

    def export_db(self):
        """Выгрузка БД текущей процедуры."""
        db_path = get_db_path()
        stamp = datetime.now().strftime("%Y-%m-%d")
        default = f"permits_{self.procedure_code}_{stamp}.json"
        export_db_dialog(self, db_path, default)

    def check_updates(self):
        dlg = UpdateDialog(self, APP_VERSION, "dazvol_u_zonu.exe")
        self.wait_window(dlg)

    def _refresh_db_lists(self):
        """Обновляет списки для автодополнения при запуске."""
        pass  #ленивая загрузка при открытии combobox


# ---------------------------------------------------------------------------
# Диалоги для добавления/редактирования
# ------------------------------------------------------------------

class PersonDialog143(tk.Toplevel):
    def __init__(self, parent, person=None):
        super().__init__(parent)
        self.title("Пассажир" if person else "Добавить пассажира")
        self.geometry("400x300")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
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