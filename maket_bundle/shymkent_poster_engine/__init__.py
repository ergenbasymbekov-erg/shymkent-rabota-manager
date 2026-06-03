"""SHYMKENT_RABOTA_JOB — Mathematical Constraint Poster Engine."""

from .engine import (
    generate_poster_from_data,
    generate_poster_from_json,
    print_analysis,
)
from .language import Language, detect_language
from .parser import PosterMode, VacancyData
from .semantic_parser import SemanticParseError, parse_vacancy_semantic
from .workflow import (
    semantic_parse,
    validate_preview,
    validate_vacancy,
    vacancy_from_preview,
    vacancy_to_preview,
)

__version__ = "3.0.0"
__all__ = [
    "generate_poster_from_data",
    "generate_poster_from_json",
    "print_analysis",
    "semantic_parse",
    "parse_vacancy_semantic",
    "validate_preview",
    "validate_vacancy",
    "vacancy_from_preview",
    "vacancy_to_preview",
    "detect_language",
    "SemanticParseError",
    "VacancyData",
    "PosterMode",
    "Language",
]
