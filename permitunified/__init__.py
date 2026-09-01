# -*- coding: utf-8 -*-
"""
Единый пакет PermitUnified — генератор пропусков 14.3 / 14.5 / 19.17.1
"""
from .procedures import get_procedure, list_procedures, ProcedureConfig
from .db import UnifiedPermitDB, get_db_path
from .generator import (
    generate_all, db_find, db_find_org, db_list_fio, db_list_org,
    make_application_143, make_individual_143, make_transport_143,
    make_application_145, make_permit_cargo, make_transport_145,
    make_individual_19171, make_transport_19171
)
from .procedures import list_procedures as _list_procedures
# Re-export list_procedures from procedures module
list_procedures = _list_procedures

__all__ = [
    "get_procedure", "list_procedures", "ProcedureConfig",
    "UnifiedPermitDB", "get_db_path",
    "generate_all", "db_find", "db_find_org", "db_list_fio", "db_list_org",
    "make_application_143", "make_individual_143", "make_transport_143",
    "make_application_145", "make_permit_cargo", "make_transport_145",
    "make_individual_19171", "make_transport_19171",
]

__version__ = "0.0.1"