# -*- coding: utf-8 -*-
"""
Единый фреймворк генераторов пропусков.
Базовые классы для процедур: 14.3, 14.5, 19.17.1
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional


@dataclass
class Person:
    """Физическое лицо / Сопровождающий"""
    last_name: str = ""
    first_name: str = ""
    middle_name: str = ""
    birth_date: str = ""
    id_number: str = ""
    position: str = ""

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass
class Vehicle:
    """Транспортное средство"""
    make: str = ""
    number: str = ""

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass
class ProcedureConfig:
    """Конфигурация процедуры"""
    code: str
    name: str
    description: str
    has_application: bool = True
    has_individual_permits: bool = True
    has_transport_permits: bool = True
    has_cargo_permit: bool = False
    goal_fixed: Optional[str] = None
    goal_options: List[str] = field(default_factory=list)
    districts: List[str] = field(default_factory=list)
    signers: List[str] = field(default_factory=list)

    template_application: str = ""
    template_individual: str = ""
    template_transport: str = ""
    template_cargo: str = ""


# Общий список районов
DEFAULT_DISTRICTS = [
    "Брагинский", "Буда-Кошелевский", "Ветковский", "Добрушский",
    "Кормянский", "Наровлянский", "Хойникский", "Чечерский"
]

# Общий список должностных лиц (подписантов)
DEFAULT_SIGNERS = [
    "Заместитель начальника главного управления В.О.Шабловский",
    "Начальник отдела Соломейчук А.В.",
    "Заместитель начальника отдела Путькова Т.М.",
    "Главный специалист Гвоздарев А.А.",
    "Главный специалист Геращенко Г.Н.",
    "Главный специалист Колесан А.И.",
    "Главный специалист Курило А.В.",
    "Главный специалист Новик П.Н.",
    "Главный специалист Одиноченко И.В.",
    "Главный специалист Першко А.С.",
]

# Конфигурации процедур
PROCEDURES: Dict[str, ProcedureConfig] = {
    "14.3": ProcedureConfig(
        code="14.3",
        name="Пункт 14.3 — Благоустройство могил",
        description="Въезд для благоустройства места захоронения",
        has_application=True,
        has_individual_permits=True,
        has_transport_permits=True,
        goal_options=["благоустройство места захоронения", "посещение места захоронения"],
        districts=DEFAULT_DISTRICTS,
        signers=DEFAULT_SIGNERS,
        template_application="Заявление_14.3.docx",
        template_individual="Пропуск_индивидуальный.docx",
        template_transport="Пропуск_транспортный.docx",
    ),
    "14.5": ProcedureConfig(
        code="14.5",
        name="Пункт 14.5 — Вывоз имущества",
        description="Въезд для вывоза имущества из зоны",
        has_application=True,
        has_individual_permits=True,
        has_transport_permits=True,
        has_cargo_permit=True,
        goal_fixed="для вывоза имущества",
        districts=DEFAULT_DISTRICTS,
        signers=DEFAULT_SIGNERS,
        template_application="Заявление_14.5.docx",
        template_individual="Пропуск_индивидуальный.docx",
        template_transport="Пропуск_транспортный.docx",
        template_cargo="Пропуск_вывоз_имущества.docx",
    ),
    "19.17.1": ProcedureConfig(
        code="19.17.1",
        name="Пункт 19.17.1 — Мониторинг / Работы",
        description="Въезд для проведения мониторинга и хозяйственных работ",
        has_application=False,
        has_individual_permits=True,
        has_transport_permits=True,
        districts=DEFAULT_DISTRICTS,
        signers=DEFAULT_SIGNERS,
        template_individual="Пропуск_индивидуальный_19.17.1.docx",
        template_transport="Пропуск_транспортный_19.17.1.docx",
    ),
}


def get_procedure(code: str) -> ProcedureConfig:
    return PROCEDURES.get(code, PROCEDURES["14.3"])


def list_procedures() -> List[ProcedureConfig]:
    return list(PROCEDURES.values())
