"""Vacancy data model — structured fields for the layout engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .language import Language


class PosterMode(str, Enum):
    SINGLE = "SINGLE"
    MULTI = "MULTI"


@dataclass
class VacancyData:
    mode: PosterMode
    language: Language = Language.MIXED
    company: str = ""
    vacancy_title: str = ""
    positions: list[str] = field(default_factory=list)
    salary: str = ""
    requirements: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    phone: str = ""
    address: str = ""
    instagram: str = ""
    requirements_heading: str = ""
    responsibilities_heading: str = ""
    conditions_heading: str = ""
    multi_title: str = ""
