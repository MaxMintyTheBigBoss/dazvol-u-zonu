# -*- coding: utf-8 -*-
"""
Общий графический диалог обновления, переиспользуемый во всех генераторах.
Импортируется из app.py, app_145.py, app_19171.py.
"""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import permit_update

OWNER = "MaxMintyTheBigBoss"
REPO = "zone-permit-generators"


class UpdateDialog(tk.Toplevel):
    """Диалог обновления: 3 вкладки (онлайн, из файла, справка)."""

    def __init__(self, parent, current_version, exe_name):
        super().__init__(parent)
        self.title("Проверка обновлений")
        self.geometry("560x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.current_version = current_version
        self.exe_name = exe_name

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        # --- Вкладка 1: онлайн ---
        tab1 = ttk.Frame(nb)
        nb.add(tab1, text="🌐 Онлайн")
        ttk.Button(tab1, text="Проверить на GitHub",
                   command=self._check_online).pack(pady=10)
        self.online_text = tk.Text(tab1, wrap="word", height=14, state="disabled")
        self.online_text.pack(fill="both", expand=True, padx=8, pady=8)

        # --- Вкладка 2: из файла ---
        tab2 = ttk.Frame(nb)
        nb.add(tab2, text="📁 Из файла")
        info = (
            "1. Скачайте новую версию программы (флешка, почта и т.п.).\n"
            "2. Сохраните как .zip (без распаковки!).\n"
            "3. Нажмите 'Выбрать файл…' и укажите этот .zip.\n"
            "4. Нажмите 'Установить обновление' — программа сделает\n"
            "   бэкап текущего .exe и заменит файлы из архива.\n"
            "5. Перезапустите программу.\n"
        )
        ttk.Label(tab2, text=info, justify="left").pack(padx=12, pady=12, anchor="w")
        self.file_path_var = tk.StringVar()
        row = ttk.Frame(tab2)
        row.pack(fill="x", padx=12)
        ttk.Entry(row, textvariable=self.file_path_var, state="readonly").pack(
            side="left", fill="x", expand=True)
        ttk.Button(row, text="Выбрать…", command=self._pick_zip).pack(
            side="left", padx=4)
        ttk.Button(tab2, text="Установить обновление",
                   command=self._apply_local).pack(pady=8)
        self.local_status = ttk.Label(tab2, text="", foreground="gray")
        self.local_status.pack()

        # --- Вкладка 3: справка ---
        tab3 = ttk.Frame(nb)
        nb.add(tab3, text="ℹ️ О обновлениях")
        help_txt = (
            f"Текущая версия: {current_version}\n\n"
            "Кнопка 'Обновления' проверяет наличие новой версии на GitHub\n"
            "(нужен интернет). Если у вас нет интернета на рабочем\n"
            "компьютере — используйте вкладку 'Из файла':\n"
            "    1) Скачайте .zip обновления на любом устройстве\n"
            "    2) Перенесите на флешке\n"
            "    3) Укажите путь к .zip в этой вкладке\n\n"
            "Все бэкапы хранятся в подпапке _backup/.\n"
            "При ошибке обновления программа автоматически\n"
            "восстанавливается из последней резервной копии.\n\n"
            f"Репозиторий: github.com/{OWNER}/{REPO}\n"
            "Email: al.vl.solo@yandex.by"
        )
        ttk.Label(tab3, text=help_txt, justify="left", wraplength=520).pack(
            padx=12, pady=12, anchor="nw")

    def _set_online_text(self, text):
        self.online_text.configure(state="normal")
        self.online_text.delete("1.0", "end")
        self.online_text.insert("1.0", text)
        self.online_text.configure(state="disabled")

    def _check_online(self):
        self._set_online_text("Проверяю GitHub…")
        self.update_idletasks()
        chk = permit_update.OnlineChecker(OWNER, REPO)
        result = chk.check(self.current_version)
        if result is None:
            self._set_online_text(
                "Не удалось подключиться к GitHub.\n"
                "Проверьте интернет-соединение или используйте вкладку 'Из файла'.")
            return
        if not result["has_update"]:
            self._set_online_text(
                f"Вы используете последнюю версию ({self.current_version}).\n\n"
                f"Последний релиз: {result['tag']}")
            return
        text = (
            f"Доступно обновление!\n\n"
            f"Текущая:   {self.current_version}\n"
            f"Доступна:  {result['tag']}  ({result['name']})\n\n"
            f"Скачайте архив по ссылке и установите через вкладку 'Из файла':\n"
            f"{result['html_url']}\n\n"
            "Что нового:\n" + (result["body"][:500] or "(без описания)"))
        self._set_online_text(text)

    def _pick_zip(self):
        path = filedialog.askopenfilename(
            title="Выберите файл обновления (.zip)",
            filetypes=[("ZIP-архив", "*.zip"), ("Все файлы", "*.*")])
        if path:
            self.file_path_var.set(path)
            self.local_status.configure(text="", foreground="gray")

    def _apply_local(self):
        path = self.file_path_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("Обновление", "Сначала выберите файл обновления.")
            return
        if not messagebox.askyesno(
            "Подтверждение",
            "Установить обновление из файла?\n"
            "Будет создан бэкап текущего exe в подпапке _backup/."):
            return
        updater = permit_update.LocalUpdater(self.exe_name)
        ok, msg = updater.apply(path)
        if ok:
            self.local_status.configure(text="✅ " + msg, foreground="green")
            messagebox.showinfo(
                "Обновление установлено",
                msg + "\n\nПерезапустите программу для применения изменений.")
        else:
            self.local_status.configure(text="❌ " + msg, foreground="red")
            messagebox.showerror("Ошибка обновления", msg)


def export_db_dialog(app, db_path, default_name):
    """Универсальный диалог выгрузки БД в JSON/CSV/Excel.

    app — родительское окно (для диалогов и сообщений).
    db_path — путь к .sqlite.
    default_name — имя файла по умолчанию.
    """
    if not os.path.exists(db_path):
        messagebox.showinfo("Экспорт БД", "База данных пуста или не создана.")
        return
    import permit_db as pdb_mod
    from datetime import datetime
    stamp = datetime.now().strftime("%Y-%m-%d")
    out = filedialog.asksaveasfilename(
        title="Выгрузить базу пропусков",
        defaultextension=".json",
        initialfile=default_name.replace("XXXX", stamp),
        filetypes=[("JSON", "*.json"), ("Excel", "*.xlsx"), ("CSV", "*.csv")])
    if not out:
        return
    ext = os.path.splitext(out)[1].lower()
    fmt = {"xlsx": "excel", ".xlsx": "excel",
           "csv": "csv", ".csv": "csv"}.get(ext, "json")
    try:
        db = pdb_mod.PermitDB(db_path)
        res = db.export(out, fmt=fmt)
        db.close()
        if fmt == "excel" and res is None:
            messagebox.showerror("Экспорт БД",
                "Не удалось экспортировать в Excel (нужен модуль openpyxl).\n"
                "Установите: pip install openpyxl")
            return
        messagebox.showinfo("Экспорт БД", "База выгружена:\n" + out)
    except Exception as e:
        messagebox.showerror("Экспорт БД", "Ошибка: %s" % e)