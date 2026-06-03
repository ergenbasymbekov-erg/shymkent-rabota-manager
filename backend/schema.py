from typing import Literal, Optional

from pydantic import BaseModel, Field

from pipeline_debug import PipelineDebugTrace


class PositionGroup(BaseModel):
    """One position with its own hiring details — never merge across positions."""
    position: str = ""
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    salary: str = ""
    schedule: list[str] = Field(default_factory=list)


class VacancyJSON(BaseModel):
    language: str = ""
    company: str = ""
    vacancy_type: Literal["SINGLE_POSITION", "MULTI_POSITION", "single", "multi"] = "SINGLE_POSITION"
    vacancy_title: str = ""
    positions: list[str] = Field(default_factory=list)
    position_groups: list[PositionGroup] = Field(default_factory=list)
    salary: str = ""
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    phones_display: list[str] = Field(default_factory=list)
    address: str = ""
    address_notes: str = ""
    instagram: str = ""
    notes: str = ""
    unsorted_review: list[str] = Field(default_factory=list)


class ParseRequest(BaseModel):
    raw_text: str


class ParseResponse(BaseModel):
    data: VacancyJSON
    mode: Literal["gpt"] = "gpt"
    model: str = ""


class ReviewRequest(BaseModel):
    raw_text: str
    data: VacancyJSON


class ReviewResult(BaseModel):
    verdict: Literal["PASS", "NEEDS_REVIEW"] = "NEEDS_REVIEW"
    score: int = Field(ge=0, le=100, default=0)
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    review: ReviewResult
    model: str = ""


class EditorFields(BaseModel):
    company: str = ""
    vacancy_type: Literal["SINGLE_POSITION", "MULTI_POSITION"] = "SINGLE_POSITION"
    vacancy_title: str = ""
    positions: list[str] = Field(default_factory=list)
    position_groups: list[PositionGroup] = Field(default_factory=list)
    salary: str = ""
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    phones_display: list[str] = Field(default_factory=list)
    address: str = ""
    address_notes: str = ""
    instagram: str = ""
    notes: str = ""
    unsorted_review: list[str] = Field(default_factory=list)


class EditorResult(BaseModel):
    before: str = ""
    after: str = ""
    fields: EditorFields = Field(default_factory=EditorFields)
    review_required: bool = False


class EditRequest(BaseModel):
    raw_text: str
    data: VacancyJSON


class EditResponse(BaseModel):
    editor: EditorResult
    model: str = ""


class StructuredData(BaseModel):
    """Phase 3: plain arrays only — no bullets or formatting in values."""
    company: str = ""
    vacancy_type: Literal["SINGLE_POSITION", "MULTI_POSITION"] = "SINGLE_POSITION"
    vacancy_title: str = ""
    positions: list[str] = Field(default_factory=list)
    position_groups: list[PositionGroup] = Field(default_factory=list)
    salary: str = ""
    address: str = ""
    address_notes: str = ""
    phones: list[str] = Field(default_factory=list)
    phones_display: list[str] = Field(default_factory=list)
    instagram: str = ""
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    notes: str = ""
    unsorted_review: list[str] = Field(default_factory=list)


class PipelineStageTrace(BaseModel):
    """One step in RAW → PARSER → EDITOR → … pipeline for UNKNOWN debugging."""
    stage: str = ""
    module: str = ""
    positions: list[str] = Field(default_factory=list)
    positions_raw: list[str] = Field(default_factory=list)
    vacancy_title: str = ""
    note: str = ""


class UnknownTraceResult(BaseModel):
    """Why vacancy_title became UNKNOWN_POSITION and where positions were lost."""
    is_unknown: bool = False
    unknown_reason: str = ""
    assigned_by_module: str = ""
    positions_before_unknown: list[str] = Field(default_factory=list)
    pipeline: list[PipelineStageTrace] = Field(default_factory=list)
    lost_at_stage: str = ""
    detail: str = ""


class ValidationResult(BaseModel):
    """Global validation flags — gate approval and poster generation."""
    phone_error: bool = False
    unknown_position: bool = False
    language_error: bool = False
    critical_data_missing: bool = False
    discrimination_flag: bool = False
    review_required: bool = False
    can_approve: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CompletenessResult(BaseModel):
    """Vacancy completeness score — runs after AI Review, before approval."""
    score: int = Field(ge=0, le=100, default=0)
    max_score: int = 100
    status: Literal["READY", "REVIEW", "INCOMPLETE"] = "INCOMPLETE"
    indicator: str = "🔴"
    missing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    field_scores: dict[str, int] = Field(default_factory=dict)
    can_poster: bool = False


class QualityResult(BaseModel):
    confidence: int = Field(ge=0, le=100, default=0)
    information_lost: bool = False
    information_duplicated: bool = False
    information_invented: bool = False
    mistakes_fixed: bool = True
    vacancy_title_logical: bool = True
    company_logical: bool = True
    editorial_clean: bool = True
    language_preserved: bool = True
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    review_required: bool = False
    position_unknown: bool = False


class NormalizeRequest(BaseModel):
    raw_text: str


class NormalizeResponse(BaseModel):
    before: str = ""
    after: str = ""
    structured: StructuredData = Field(default_factory=StructuredData)
    parsed: VacancyJSON = Field(default_factory=VacancyJSON)
    quality: QualityResult = Field(default_factory=QualityResult)
    review: ReviewResult = Field(default_factory=ReviewResult)
    validation: ValidationResult = Field(default_factory=ValidationResult)
    completeness: CompletenessResult = Field(default_factory=CompletenessResult)
    review_required: bool = False
    can_approve: bool = False
    manager_review_reason: str = ""
    unknown_trace: UnknownTraceResult = Field(default_factory=UnknownTraceResult)
    pipeline_debug: PipelineDebugTrace = Field(default_factory=PipelineDebugTrace)
    model: str = ""


class GenerateRequest(BaseModel):
    """Approved structured JSON only — used after manager approval."""
    structured: StructuredData
    language: str = ""


class GenerateAllResult(BaseModel):
    poster_text: str = ""
    telegram_text: str = ""
    whatsapp_text: str = ""
    language: str = ""


class PosterGenerateRequest(BaseModel):
    structured: StructuredData
    language: str = ""


class PosterGenerateResponse(BaseModel):
    png_url: str = ""
    filename: str = ""
    errors: list[str] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    generated: GenerateAllResult = Field(default_factory=GenerateAllResult)


class RewriteRequest(BaseModel):
    raw_text: str


class RewriteOutputs(BaseModel):
    poster_text: str = ""
    telegram_text: str = ""
    whatsapp_text: str = ""


class RewriteResponse(BaseModel):
    before: str = ""
    clean_full_text: str = ""
    outputs: RewriteOutputs = Field(default_factory=RewriteOutputs)
    poster_png_url: str = ""
    poster_png_filename: str = ""
    poster_error: str = ""
    poster_debug: dict = Field(default_factory=dict)
    model: str = ""


class TemplateGenerateRequest(BaseModel):
    text: str


class TelegramButton(BaseModel):
    text: str
    url: str


class TemplateOutputs(BaseModel):
    telegram_text: str = ""
    whatsapp_text: str = ""
    telegram_buttons: list[TelegramButton] = Field(default_factory=list)


class TemplateGenerateResponse(BaseModel):
    source_text: str = ""
    outputs: TemplateOutputs = Field(default_factory=TemplateOutputs)
    poster_png_url: str = ""
    poster_png_filename: str = ""
    poster_warning: str = ""
    poster_debug: dict = Field(default_factory=dict)
    error: str = ""


class ManagerPublishRequest(BaseModel):
    text: str


class ManagerPublishResponse(BaseModel):
    ok: bool = True
    channel: str = ""
    message: str = ""
    poster_used: bool = False
