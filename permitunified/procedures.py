# -*- coding: utf-8 -*-
"""
Единый фреймворк генераторов пропусков.
Базовые классы для процедур: 14.3, 14.5, 19.17.1
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import os

@dataclass
class Person:
    """Физическое лицо"""
    last_name: str = ""
    first_name: str = ""
    middle_name: str = ""
    birth_date: str = ""
    position: str = ""  # для 19.17.1

@dataclass
class Vehicle:
    """Автомобиль"""
    make: str = ""
    number: str = ""

@dataclass
class ProcedureConfig:
    """Конфигурация процедуры"""
    code: str                    # "14.3", "14.5", "19.17.1"
    name: str                    # Отображаемое имя
    description: str             # Описание для экрана выбора
    has_application: bool = True # Генерировать заявление
    has_individual_permits: bool = True
    has_transport_permits: bool = True
    has_cargo_permit: bool = False
    goal_fixed: Optional[str] = None  # Фиксированная цель (для 14.5)
    goal_options: List[str] = field(default_factory=list)
    districts: List[str] = field(default_factory=list)
    signers: List[str] = field(default_factory=list)
    # Шаблоны
    template_application: str = ""
    template_individual: str = ""
    template_transport: str = ""
    template_cargo: str = ""
    # Поля формы
    fields: List[Dict] = field(default_factory=list)  # Динамическое описание полей

# Предустановленные конфигурации
PROCEDURES = {
    "14.3": ProcedureConfig(
        code="14.3",
        name="Пункт 14.3 — Благоустройство могил",
        description="Въезд для благоустройства места захоронения",
        has_application=True,
        has_individual_permits=True,
        has_transport_permits=True,
        goal_options=["благоустройство места захоронения", "свой вариант"],
        districts=[
            "Брагинский", "Буда-Кошелевский", "Ветковский", "Добрушский",
            "Кормянский", "Наровлянский", "Хойникский", "Чечерский"
        ],
        signers=[
            "Заместитель начальника отдела Путькова Т.М.",
            "Начальник отдела Соломейчук А.В.",
            "Заместитель начальника главного управления В.О.Шабловский",
            "Главный специалист Гвоздарев А.А.",
            "Главный специалист Геращенко Г.Н.",
            "Главный специалист Колесан А.И.",
            "Главный специалист Курило А.В.",
            "Главный специалист Новик П.Н.",
            "Главный специалист Одиноченко И.В.",
            "Главный специалист Першко А.С.",
        ],
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
        districts=[
            "Брагинский", "Буда-Кошелевский", "Ветковский", "Добрушский",
            "Кормянский", "Наровлянский", "Хойникский", "Чечерский"
        ],
        signers=[
            "Заместитель начальника отдела Путькова Т.М.",
            "Начальник отдела Соломейчук А.В.",
            "Заместитель начальника главного управления В.О.Шабловский",
            "Главный специалист Гвоздарев А.А.",
            "Главный специалист Геращенко Г.Н.",
            "Главный специалист Колесан А.И.",
            "Главный специалист Курило А.В.",
            "Главный специалист Новик П.Н.",
            "Главный специалист Одиноченко И.В.",
            "Главный специалист Першко А.С.",
        ],
        template_application="Заявление_14.5.docx",
        template_individual="Пропуск_индивидуальный.docx",
        template_transport="Пропуск_транспортный.docx",
        template_cargo="Пропуск_вывоз_имущества.docx",
    ),
    "19.17.1": ProcedureConfig(
        code="19.17.1",
        name="Пункт 19.17.1 — Мониторинг/Работы",
        description="Въезд для проведения мониторинга и работ",
        has_application=False,  # Только пропуска
        has_individual_permits=True,
        has_transport_permits=True,
        districts=[
            "Брагинский", "Буда-Кошелевский", "Ветковский", "Добрушский",
            "Кормянский", "Наровлянский", "Хойникский", "Чечерский"
        ],
        signers=[
            "Заместитель начальника отдела Путькова Т.М.",
            "Начальник отдела Соломейчук А.В.",
            "Заместитель начальника главного управления В.О.Шабловский",
            "Главный специалист Гвоздарев А.А.",
            "Главный специалист Геращенко Г.Н.",
            "Главный специалист Колесан А.И.",
            "Главный специалист Курило А.В.",
            "Главный специалист Новик П.Н.",
            "Главный специалист Одиноченко И.В.",
            "Главный специалист Першко А.С.",
        ],
        template_individual="Пропуск_индивидуальный_19.17.1.docx",
        template_transport="Пропуск_транспортный_19.17.1.docx",
    ),
}

def get_procedure(code: str) -> ProcedureConfig:
    return PROCEDURES.get(code, PROCEDURES["14.3"])

def list_procedures() -> List[ProcedureConfig]:
    return list(PROCEDURES.values())