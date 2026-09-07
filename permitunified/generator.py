# -*- coding: utf-8 -*-
"""
Унифицированный генератор документов для всех процедур.
Использует procedures.py (конфиг) и db.py (БД).
"""
import json
import logging
import os
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from permitunified.db import UnifiedPermitDB, get_db_path
from permitunified.procedures import ProcedureConfig, get_procedure

logger = logging.getLogger(__name__)

# Регулярное выражение для поиска плейсхолдеров
_PH_RE = re.compile(r"\*{0,2}(Placeholder_\d+(?:\.\d+)?)\*{0,2}")


def resource_path() -> str:
    """Путь к ресурсам (совместимо с PyInstaller)."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.argv[0])))
    else:
        base = Path(__file__).resolve().parent.parent
    return str(base)


def template_dir() -> str:
    return os.path.join(resource_path(), "templates")


def sanitize(s: str, default: str = "файл") -> str:
    illegal = '<>:"/\\|?*'
    cleaned = "".join(c for c in str(s) if c not in illegal).strip()
    return cleaned or default


def today_dmy() -> str:
    return datetime.now().strftime("%d.%m.%Y")


# ---------------------------------------------------------------------------
# Замена плейсхолдеров (подчёркивает только подставляемое значение)
# ---------------------------------------------------------------------------
def _inline_replace(paragraph, mapping: Dict[str, str]) -> None:
    runs = paragraph._p.findall(qn("w:r"))
    if not runs:
        return

    # Собираем сегменты: (rpr, text)
    segments = []
    full_parts = []
    for r in runs:
        texts = [t.text or "" for t in r.findall(qn("w:t"))]
        txt = "".join(texts)
        rpr = r.find(qn("w:rPr"))
        segments.append((rpr, txt))
        full_parts.append(txt)
    full = "".join(full_parts)

    if "Placeholder_" not in full:
        return

    # Карта позиций
    boundaries = []
    acc = 0
    for _, txt in segments:
        boundaries.append(acc)
        acc += len(txt)

    def rpr_at(pos: int):
        idx = 0
        for i, b in enumerate(boundaries):
            if pos >= b:
                idx = i
            else:
                break
        return segments[idx][0]

    matches = list(_PH_RE.finditer(full))
    new_segments = []
    pos = 0
    replaced = False

    for m in matches:
        tok = m.group(1)
        if tok not in mapping:
            continue
        val = str(mapping[tok])
        s, e = m.span()

        if s > pos:
            seg_txt = full[pos:s]
            if seg_txt:
                new_segments.append((rpr_at(pos), seg_txt, False))

        # Заменяемое значение подчёркивается
        new_segments.append((rpr_at(s), val, True))
        pos = e
        replaced = True

    if not replaced:
        return

    if pos < len(full):
        new_segments.append((rpr_at(pos), full[pos:], False))

    # Замена run'ов
    for r in runs:
        paragraph._p.remove(r)

    for rpr, txt, underline in new_segments:
        if not txt:
            continue
        run_el = OxmlElement("w:r")
        if rpr is not None:
            run_el.append(deepcopy(rpr))
        if underline:
            rpr_u = run_el.find(qn("w:rPr"))
            if rpr_u is None:
                rpr_u = OxmlElement("w:rPr")
                run_el.append(rpr_u)
            u = rpr_u.find(qn("w:u"))
            if u is None:
                u = OxmlElement("w:u")
                rpr_u.append(u)
            u.set(qn("w:val"), "single")
        t = OxmlElement("w:t")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = txt
        run_el.append(t)
        paragraph._p.append(run_el)


def fill_doc(doc: Document, mapping: Dict[str, str]) -> Document:
    """Заменяет плейсхолдеры во всех параграфах и таблицах документа."""
    for para in doc.paragraphs:
        _inline_replace(para, mapping)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    _inline_replace(para, mapping)
    return doc


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def join_districts(districts: List[str]) -> str:
    return ", ".join(d for d in districts if d)


def join_objects(objects: List[Dict[str, str]], custom: str = "") -> str:
    lst = []
    for o in objects:
        if isinstance(o, dict):
            v = (o.get("object") or "").strip()
        else:
            v = str(o).strip()
        if v:
            lst.append(v)
    if custom and custom.strip():
        lst.append(custom.strip())
    return "; ".join(lst)


def load_reference() -> List[Dict[str, str]]:
    """Справочник объектов: список {district, object}."""
    path = os.path.join(template_dir(), "справочник.docx")
    entries: List[Dict[str, str]] = []
    if not os.path.exists(path):
        return entries
    try:
        doc = Document(path)
        for p in doc.paragraphs:
            parts = [t for t in p.text.split("\t") if t.strip()]
            if len(parts) >= 3:
                district = parts[0].strip()
                obj = "кладбище о.н.п. " + parts[2].strip()
                if district and obj:
                    entries.append({"district": district, "object": obj})
    except Exception as e:
        logger.error(f"Ошибка чтения справочника: {e}")
    return entries


def filter_objects_by_districts(reference: List[Dict[str, str]], districts: List[str]) -> List[Dict[str, str]]:
    allowed = set(districts)
    return [r for r in reference if r["district"] in allowed]


# ---------------------------------------------------------------------------
# Сборщики словарей замен (Mappings)
# ---------------------------------------------------------------------------

def build_mapping_143(data: Dict) -> Dict:
    districts = data.get("districts", [])
    mapping = {
        "Placeholder_1.1": data.get("last_name", ""),
        "Placeholder_1.2": data.get("first_name", ""),
        "Placeholder_1.3": data.get("middle_name", ""),
        "Placeholder_2": data.get("birth_date", ""),
        "Placeholder_3": data.get("id_number", ""),
        "Placeholder_4": join_districts(districts),
        "Placeholder_5": data.get("objects", ""),
        "Placeholder_6": data.get("goal", ""),
        "Placeholder_7": data.get("date_from", ""),
        "Placeholder_8": data.get("date_to", ""),
        "Placeholder_9": data.get("app_date") or today_dmy(),
        "Placeholder_12": data.get("car_make", ""),
        "Placeholder_13": data.get("car_number", ""),
        "Placeholder_20": data.get("issued_by", ""),
    }
    for i in range(3):
        mapping[f"Placeholder_4.{i+1}"] = districts[i] if i < len(districts) else ""
    return mapping


def build_mapping_145(data: Dict) -> Dict:
    districts = data.get("districts", [])
    mapping = {
        "Placeholder_1.1": data.get("last_name", ""),
        "Placeholder_1.2": data.get("first_name", ""),
        "Placeholder_1.3": data.get("middle_name", ""),
        "Placeholder_2": data.get("birth_date", ""),
        "Placeholder_3": data.get("id_number", ""),
        "Placeholder_4": join_districts(districts),
        "Placeholder_5": data.get("objects", ""),
        "Placeholder_6": "для вывоза имущества",
        "Placeholder_7": data.get("date_from", ""),
        "Placeholder_8": data.get("date_to", ""),
        "Placeholder_12": data.get("car_make", ""),
        "Placeholder_13": data.get("car_number", ""),
        "Placeholder_20": data.get("issued_by", ""),
        "Placeholder_21": data.get("cargo", ""),
    }
    for i in range(3):
        mapping[f"Placeholder_4.{i+1}"] = districts[i] if i < len(districts) else ""
    return mapping


def build_mapping_19171_individual(data: Dict, person: Dict) -> Dict:
    districts = data.get("districts", [])
    return {
        "Placeholder_10.1": person.get("last_name", ""),
        "Placeholder_10.2": person.get("first_name", ""),
        "Placeholder_10.3": person.get("middle_name", ""),
        "Placeholder_22": data.get("org_info", ""),
        "Placeholder_25": person.get("position", ""),
        "Placeholder_4": join_districts(districts),
        "Placeholder_5": data.get("objects", ""),
        "Placeholder_6": data.get("goal", ""),
        "Placeholder_7": data.get("date_from", ""),
        "Placeholder_8": data.get("date_to", ""),
        "Placeholder_20": data.get("issued_by", ""),
    }


def build_mapping_19171_transport(data: Dict, vehicle: Dict) -> Dict:
    districts = data.get("districts", [])
    org_rep_last = data.get("org_rep_last", "")
    org_rep_first = data.get("org_rep_first", "")
    org_rep_middle = data.get("org_rep_middle", "")
    if not org_rep_last and not org_rep_first and not org_rep_middle:
        org_rep_last = data.get("org_info", "")

    return {
        "Placeholder_1.1": org_rep_last,
        "Placeholder_1.2": org_rep_first,
        "Placeholder_1.3": org_rep_middle,
        "Placeholder_4": join_districts(districts),
        "Placeholder_5": data.get("objects", ""),
        "Placeholder_6": data.get("goal", ""),
        "Placeholder_7": data.get("date_from", ""),
        "Placeholder_8": data.get("date_to", ""),
        "Placeholder_12": vehicle.get("make", ""),
        "Placeholder_13": vehicle.get("number", ""),
        "Placeholder_20": data.get("issued_by", ""),
    }


# ---------------------------------------------------------------------------
# Генераторы отдельных документов
# ---------------------------------------------------------------------------

def make_application_143(data: Dict) -> Document:
    doc = Document(os.path.join(template_dir(), "Заявление_14.3.docx"))
    mapping = build_mapping_143(data)
    fill_doc(doc, mapping)
    return doc


def make_individual_143(data: Dict, person: Optional[Dict] = None) -> Document:
    person = person if person is not None else data
    doc = Document(os.path.join(template_dir(), "Пропуск_индивидуальный.docx"))
    mapping = {
        "Placeholder_1.1": person.get("last_name", ""),
        "Placeholder_1.2": person.get("first_name", ""),
        "Placeholder_1.3": person.get("middle_name", ""),
        "Placeholder_4": join_districts(data.get("districts", [])),
        "Placeholder_5": data.get("objects", ""),
        "Placeholder_6": data.get("goal", ""),
        "Placeholder_7": data.get("date_from", ""),
        "Placeholder_8": data.get("date_to", ""),
        "Placeholder_20": data.get("issued_by", ""),
    }
    fill_doc(doc, mapping)
    return doc


def make_transport_143(data: Dict) -> Document:
    doc = Document(os.path.join(template_dir(), "Пропуск_транспортный.docx"))
    mapping = {
        "Placeholder_1.1": data.get("last_name", ""),
        "Placeholder_1.2": data.get("first_name", ""),
        "Placeholder_1.3": data.get("middle_name", ""),
        "Placeholder_4": join_districts(data.get("districts", [])),
        "Placeholder_5": data.get("objects", ""),
        "Placeholder_6": data.get("goal", ""),
        "Placeholder_7": data.get("date_from", ""),
        "Placeholder_8": data.get("date_to", ""),
        "Placeholder_12": data.get("car_make", ""),
        "Placeholder_13": data.get("car_number", ""),
        "Placeholder_20": data.get("issued_by", ""),
    }
    fill_doc(doc, mapping)
    return doc


def make_application_145(data: Dict) -> Document:
    doc = Document(os.path.join(template_dir(), "Заявление_14.5.docx"))
    mapping = build_mapping_145(data)
    fill_doc(doc, mapping)
    return doc


def make_permit_cargo(data: Dict) -> Document:
    doc = Document(os.path.join(template_dir(), "Пропуск_вывоз_имущества.docx"))
    mapping = {
        "Placeholder_1.1": data.get("last_name", ""),
        "Placeholder_1.2": data.get("first_name", ""),
        "Placeholder_1.3": data.get("middle_name", ""),
        "Placeholder_4": join_districts(data.get("districts", [])),
        "Placeholder_5": data.get("objects", ""),
        "Placeholder_7": data.get("date_from", ""),
        "Placeholder_8": data.get("date_to", ""),
        "Placeholder_20": data.get("issued_by", ""),
        "Placeholder_21": data.get("cargo", ""),
    }
    fill_doc(doc, mapping)
    return doc


def make_transport_145(data: Dict) -> Document:
    doc = Document(os.path.join(template_dir(), "Пропуск_транспортный.docx"))
    mapping = {
        "Placeholder_1.1": data.get("last_name", ""),
        "Placeholder_1.2": data.get("first_name", ""),
        "Placeholder_1.3": data.get("middle_name", ""),
        "Placeholder_4": join_districts(data.get("districts", [])),
        "Placeholder_5": data.get("objects", ""),
        "Placeholder_6": "для вывоза имущества",
        "Placeholder_7": data.get("date_from", ""),
        "Placeholder_8": data.get("date_to", ""),
        "Placeholder_12": data.get("car_make", ""),
        "Placeholder_13": data.get("car_number", ""),
        "Placeholder_20": data.get("issued_by", ""),
    }
    fill_doc(doc, mapping)
    return doc


def make_individual_19171(data: Dict, person: Dict) -> Document:
    doc = Document(os.path.join(template_dir(), "Пропуск_индивидуальный_19.17.1.docx"))
    mapping = build_mapping_19171_individual(data, person)
    fill_doc(doc, mapping)
    return doc


def make_transport_19171(data: Dict, vehicle: Dict) -> Document:
    doc = Document(os.path.join(template_dir(), "Пропуск_транспортный_19.17.1.docx"))
    mapping = build_mapping_19171_transport(data, vehicle)
    fill_doc(doc, mapping)
    return doc


# ---------------------------------------------------------------------------
# Главный вызов генерации пакета
# ---------------------------------------------------------------------------

def generate_all(data: Dict, output_dir: Optional[str] = None, procedure_code: str = "14.3") -> List[str]:
    """Главный генератор пропусков."""
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(get_db_path()), "output")

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = os.path.join(output_dir, stamp)
    os.makedirs(out, exist_ok=True)

    created = []
    proc = get_procedure(procedure_code)

    if procedure_code == "19.17.1":
        base_name = sanitize(data.get("org_short", "Организация"), "Организация")
    else:
        base_name = sanitize(data.get("last_name", "Заявитель"), "Заявитель")

    # 1. Заявления
    if proc.has_application:
        doc = None
        if procedure_code == "14.3":
            doc = make_application_143(data)
            fname = f"Заявление_{base_name}.docx"
        elif procedure_code == "14.5":
            doc = make_application_145(data)
            fname = f"Заявление_14.5_{base_name}.docx"

        if doc:
            p = os.path.join(out, fname)
            doc.save(p)
            created.append(p)

    # 2. Индивидуальные пропуска
    if proc.has_individual_permits:
        if procedure_code == "19.17.1":
            for i, person in enumerate(data.get("persons", [])):
                doc = make_individual_19171(data, person)
                lname = sanitize(person.get("last_name", f"Лицо{i+1}"))
                p = os.path.join(out, f"Пропуск_Индивидуальный_{lname}.docx")
                doc.save(p)
                created.append(p)
        else:
            # Заявитель
            doc = make_individual_143(data)
            p = os.path.join(out, f"Пропуск_Заявитель_{base_name}.docx")
            doc.save(p)
            created.append(p)
            # Пассажиры
            for person in data.get("persons", []):
                plname = sanitize(person.get("last_name", "Пассажир"))
                doc = make_individual_143(data, person)
                p = os.path.join(out, f"Пропуск_Пассажир_{plname}.docx")
                doc.save(p)
                created.append(p)

    # 3. Грузовой пропуск (только 14.5)
    if proc.has_cargo_permit:
        doc = make_permit_cargo(data)
        p = os.path.join(out, f"Пропуск_ВывозИмущества_{base_name}.docx")
        doc.save(p)
        created.append(p)

    # 4. Транспортные пропуска
    if proc.has_transport_permits:
        if procedure_code == "19.17.1":
            for i, vehicle in enumerate(data.get("vehicles", [])):
                doc = make_transport_19171(data, vehicle)
                car = sanitize(vehicle.get("number", "") or f"Авто{i+1}")
                p = os.path.join(out, f"Пропуск_Транспорт_{car}.docx")
                doc.save(p)
                created.append(p)
        else:
            if data.get("car_make", "").strip() or data.get("car_number", "").strip():
                doc = make_transport_143(data) if procedure_code == "14.3" else make_transport_145(data)
                car = sanitize(data.get("car_number", "") or "Авто")
                p = os.path.join(out, f"Пропуск_Транспорт_{car}.docx")
                doc.save(p)
                created.append(p)

    # Сохранение в БД
    _db_remember(data, procedure_code)

    return created


# ---------------------------------------------------------------------------
# Безопасное взаимодействие с БД без утечек ресурсов
# ---------------------------------------------------------------------------

def _db_remember(data: Dict, procedure_code: str) -> None:
    db = UnifiedPermitDB(get_db_path())
    try:
        legacy_map = {
            "14.3": ("permit_history.json", "fio"),
            "14.5": ("permit_history_145.json", "fio"),
            "19.17.1": ("permit_history_19171.json", "org"),
        }
        if procedure_code in legacy_map:
            legacy_file, stype = legacy_map[procedure_code]
            legacy_path = os.path.join(os.path.dirname(get_db_path()), legacy_file)
            if os.path.exists(legacy_path):
                db.migrate_from_json(legacy_path, procedure_code, stype)

        if procedure_code == "19.17.1":
            org_key = (data.get("org_short", "") or data.get("org_info", "")).strip().lower()
            rec = {
                "org_key": org_key,
                "org_info": data.get("org_info", ""),
                "org_short": data.get("org_short", ""),
                "org_rep_last": data.get("org_rep_last", ""),
                "org_rep_first": data.get("org_rep_first", ""),
                "org_rep_middle": data.get("org_rep_middle", ""),
                "goal": data.get("goal", ""),
                "districts": data.get("districts", []),
                "objects": data.get("objects", ""),
                "include_pgrez": data.get("include_pgrez", False),
                "custom_object": data.get("custom_object", ""),
                "date_from": data.get("date_from", ""),
                "date_to": data.get("date_to", ""),
                "issued_by": data.get("issued_by", ""),
                "persons": data.get("persons", []),
                "vehicles": data.get("vehicles", []),
            }
            db.upsert(rec, procedure_code, "org")
        else:
            rec = {
                "last_name": data.get("last_name", ""),
                "first_name": data.get("first_name", ""),
                "middle_name": data.get("middle_name", ""),
                "birth_date": data.get("birth_date", ""),
                "id_number": data.get("id_number", ""),
                "cargo": data.get("cargo", ""),
                "goal": data.get("goal", ""),
                "districts": data.get("districts", []),
                "objects": data.get("objects", ""),
                "car_make": data.get("car_make", ""),
                "car_number": data.get("car_number", ""),
            }
            db.upsert(rec, procedure_code, "fio")
    finally:
        db.close()


def db_find(fio: str, procedure_code: str) -> Optional[Dict]:
    db = UnifiedPermitDB(get_db_path())
    try:
        return db.find(fio, procedure_code, "fio")
    finally:
        db.close()


def db_find_org(org_key: str, procedure_code: str) -> Optional[Dict]:
    db = UnifiedPermitDB(get_db_path())
    try:
        return db.find(org_key, procedure_code, "org")
    finally:
        db.close()


def db_list_fio(procedure_code: str) -> List[str]:
    db = UnifiedPermitDB(get_db_path())
    try:
        # С заменяющим символом % для подгрузки списка при автодополнении
        return db.find_like("%", procedure_code, "fio", limit=200)
    finally:
        db.close()


def db_list_org(procedure_code: str) -> List[str]:
    db = UnifiedPermitDB(get_db_path())
    try:
        return db.find_like("%", procedure_code, "org", limit=200)
    finally:
        db.close()


def db_list_fio(procedure_code: str) -> List[str]:
    """Список ФИО для автодополнения."""
    return UnifiedPermitDB(get_db_path()).find_like("", procedure_code, "fio", limit=200)


def db_list_org(procedure_code: str) -> List[str]:
    """Список организаций для автодополнения."""
    return UnifiedPermitDB(get_db_path()).find_like("", procedure_code, "org", limit=200)