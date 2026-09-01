# -*- coding: utf-8 -*-
"""
Унифицированная SQLite база данных для всех процедур.
Одна БД с таблицей procedures для разделения по типам.
"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tkinter.messagebox as messagebox
    import tkinter.filedialog as filedialog
except ImportError:
    messagebox = None
    filedialog = None


class UnifiedPermitDB:
    """Единая база данных для всех процедур пропусков."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base = Path(__file__).parent.parent if not getattr(__import__('sys'), 'frozen', False) else Path(os.path.dirname(os.path.abspath(__import__('sys').argv[0])))
            db_path = base / "data" / "permits_unified.sqlite"
        self._path = str(db_path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        c = self._conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS permits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                procedure_code TEXT NOT NULL,    -- '14.3', '14.5', '19.17.1'
                search_key TEXT NOT NULL,        -- ключ поиска (ФИО или организация)
                search_type TEXT NOT NULL,       -- 'fio' или 'org'
                data TEXT NOT NULL,              -- JSON с полными данными
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_permits_search
            ON permits(search_key, search_type, procedure_code)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_permits_proc
            ON permits(procedure_code, created_at DESC)
        """)
        c.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # ---- Чтение ----
    def load(self, procedure_code: Optional[str] = None, search_type: Optional[str] = None) -> List[Dict]:
        """Все записи (опционально фильтруя по процедуре и типу поиска)."""
        sql = "SELECT data, search_key, procedure_code FROM permits WHERE 1=1"
        params = []
        if procedure_code:
            sql += " AND procedure_code = ?"
            params.append(procedure_code)
        if search_type:
            sql += " AND search_type = ?"
            params.append(search_type)
        sql += " ORDER BY id DESC"
        rows = self._conn.execute(sql, params).fetchall()
        out = []
        for row in rows:
            try:
                rec = json.loads(row["data"])
            except Exception:
                rec = {}
            rec["_search_key"] = row["search_key"]
            rec["_procedure_code"] = row["procedure_code"]
            out.append(rec)
        return out

    def find(self, key: str, procedure_code: str, search_type: str) -> Optional[Dict]:
        """Точный поиск по ключу (регистронезависимый)."""
        k = (key or "").strip().lower()
        if not k:
            return None
        rows = self._conn.execute(
            "SELECT data FROM permits WHERE search_key=? AND search_type=? AND procedure_code=? ORDER BY id DESC LIMIT 1",
            (k, search_type, procedure_code)
        ).fetchall()
        if not rows:
            return None
        try:
            return json.loads(rows[0]["data"])
        except Exception:
            return None

    def find_like(self, fragment: str, procedure_code: str, search_type: str, limit: int = 50) -> List[str]:
        """Поиск по фрагменту ключа (для автодополнения)."""
        frag = (fragment or "").strip().lower()
        if not frag:
            return []
        rows = self._conn.execute(
            "SELECT DISTINCT search_key FROM permits WHERE search_type=? AND procedure_code=? AND search_key LIKE ? ORDER BY search_key LIMIT ?",
            (search_type, procedure_code, "%" + frag + "%", limit)
        ).fetchall()
        return [r["search_key"] for r in rows]

    # ---- Запись ----
    def upsert(self, rec: Dict, procedure_code: str, search_type: str) -> None:
        """Добавляет/обновляет запись. search_key извлекается из rec или формируется автоматически."""
        try:
            # Определяем ключ поиска
            if "search_key" in rec and rec["search_key"]:
                key = str(rec["search_key"]).strip().lower()
            elif search_type == "fio":
                key = " ".join(str(rec.get(k, "")) for k in ("last_name", "first_name", "middle_name") if rec.get(k)).strip().lower()
            else:  # org
                key = str(rec.get("org_short") or rec.get("org_info") or rec.get("org_key") or "").strip().lower()

            if not key:
                return

            # Удаляем старые с таким же ключом для этой процедуры
            self._conn.execute(
                "DELETE FROM permits WHERE search_key=? AND search_type=? AND procedure_code=?",
                (key, search_type, procedure_code)
            )
            # Вставляем новую
            self._conn.execute(
                "INSERT INTO permits (procedure_code, search_key, search_type, data, created_at) VALUES (?,?,?,?,?)",
                (procedure_code, key, search_type, json.dumps(rec, ensure_ascii=False), datetime.now().isoformat())
            )
            self._conn.commit()
        except Exception:
            pass

    def replace_all(self, records: List[Dict], procedure_code: str, search_type: str) -> None:
        """Полная перезапись (миграция)."""
        c = self._conn
        c.execute("DELETE FROM permits WHERE procedure_code=? AND search_type=?", (procedure_code, search_type))
        for rec in records:
            self.upsert(rec, procedure_code, search_type)

    # ---- Экспорт ----
    def export(self, out_path: str, fmt: str = "json", procedure_code: Optional[str] = None) -> Optional[str]:
        """Экспорт в JSON/CSV/Excel."""
        recs = self.load(procedure_code)
        if fmt == "json":
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(recs, f, ensure_ascii=False, indent=1)
            return out_path
        if fmt == "csv":
            import csv
            fieldnames = sorted({k for r in recs for k in r.keys()}) or ["search_key"]
            with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                for r in recs:
                    w.writerow({k: r.get(k, "") for k in fieldnames})
            return out_path
        if fmt == "excel":
            try:
                from openpyxl import Workbook
            except Exception:
                return None
            wb = Workbook()
            ws = wb.active
            ws.title = "Пропуска"
            fieldnames = sorted({k for r in recs for k in r.keys()}) or ["search_key"]
            ws.append(fieldnames)
            for r in recs:
                ws.append([r.get(k, "") for k in fieldnames])
            for i, col in enumerate(fieldnames, 1):
                ws.column_dimensions[chr(64 + i if i <= 26 else 64 + i - 26)].width = 22
            wb.save(out_path)
            return out_path
        return None

    # ---- Миграция из старых JSON ----
    def migrate_from_json(self, json_path: str, procedure_code: str, search_type: str) -> int:
        """Перенос данных из старого JSON файла."""
        if not os.path.exists(json_path):
            return 0
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                recs = json.load(f)
        except Exception:
            return 0
        if not recs:
            return 0
        migrated = 0
        for rec in recs:
            self.upsert(rec, procedure_code, search_type)
            migrated += 1
        # Переименуем старый файл
        try:
            os.rename(json_path, json_path + ".migrated")
        except Exception:
            pass
        return migrated


def get_db_path() -> str:
    """Путь к БД рядом с exe/скриптом."""
    import sys
    if getattr(sys, 'frozen', False):
        base = Path(os.path.dirname(os.path.abspath(sys.argv[0])))
    else:
        base = Path(__file__).parent.parent
    return str(base / "data" / "permits_unified.sqlite")


def export_db_dialog(app, db_path, default_name):
    """Универсальный диалог выгрузки БД в JSON/CSV/Excel.

    app — родительское окно (для диалогов и сообщений).
    db_path — путь к .sqlite.
    default_name — имя файла по умолчанию.
    """
    if not os.path.exists(db_path):
        messagebox.showinfo("Экспорт БД", "База данных пуста или не создана.")
        return
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
        db = UnifiedPermitDB(db_path)
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