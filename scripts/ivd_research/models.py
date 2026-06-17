from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .constants import EVIDENCE_STRENGTH_LABELS, MATERIAL_TYPE_LABELS


class FailureType(str, Enum):
    COLLECTION_FAILED = "collection_failed"
    NO_RESULTS = "no_results"
    NO_VALID_MATERIALS = "no_valid_materials"
    DOWNLOAD_FAILED = "download_failed"
    PARSE_FAILED = "parse_failed"
    PERMISSION_REQUIRED = "permission_required"
    NEEDS_LOGIN = "needs_login"
    NEEDS_OCR = "needs_ocr"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


class DownloadFile(BaseModel):
    original_filename: str = ""
    stored_filename: str = ""
    relative_path: str = ""
    source_url: str = ""
    sha256: str = ""
    status: str = "not_downloaded"


class KeyExcerpt(BaseModel):
    text: str
    location: str = "location_unknown"
    source_path: str = ""


class Material(BaseModel):
    material_id: str
    task_id: str
    source_scenario: str
    material_type: str = "unknown"
    title: str
    source_url: str = ""
    search_keyword_or_query: str = ""
    collection_path: dict[str, Any] = Field(default_factory=dict)
    collection_time: str
    adapter_id: str = ""
    adapter_version: str = ""
    raw_fields: dict[str, Any] = Field(default_factory=dict)
    download_status: str = "not_attempted"
    download_files: list[DownloadFile] = Field(default_factory=list)
    extracted_text_status: str = "not_attempted"
    extracted_text_path: str = ""
    content_snapshot_path: str = ""
    failure_type: FailureType | None = None
    failure_reason: str = ""
    possible_duplicate_keys: list[str] = Field(default_factory=list)

    @property
    def display_labels(self) -> dict[str, str]:
        return {
            "material_type": MATERIAL_TYPE_LABELS.get(
                self.material_type, self.material_type
            )
        }


class EvidenceCard(BaseModel):
    evidence_card_id: str
    material_id: str
    material_type: str
    title: str
    translated_title: str = ""
    source_type: str = ""
    source_quality: str = ""
    publication_or_issue_date: str = ""
    identifier: str = ""
    summary: str
    tr1_file: str = ""
    primary_tag: str = ""
    secondary_tag: str = ""
    performance_tag: str = ""
    evidence_conclusion: str = ""
    exact_data: str = ""
    source_location: str = ""
    original_excerpt_or_table_marker: str = ""
    chinese_evidence_explanation: str = ""
    key_facts: list[str] = Field(default_factory=list)
    key_excerpts: list[KeyExcerpt] = Field(default_factory=list)
    taxonomy_tags: list[str] = Field(default_factory=list)
    evidence_strength: str = "needs_review"
    confidence_level: str = "待复核"
    include_in_report: bool = False
    report_usage: str = ""
    facts: list[str] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    needs_review: bool = True
    review_reasons: list[str] = Field(default_factory=lambda: ["未人工复核"])
    manual_review: dict[str, Any] = Field(default_factory=dict)

    @property
    def evidence_strength_label(self) -> str:
        return EVIDENCE_STRENGTH_LABELS.get(
            self.evidence_strength, self.evidence_strength
        )


class ScenarioStatus(BaseModel):
    scenario_id: str
    label_zh: str
    status: str = "not_started"
    material_count: int = 0
    failure_count: int = 0
    last_message: str = ""


class RecommendedAction(BaseModel):
    action_id: str
    label_zh: str
    reason_zh: str


class TaskState(BaseModel):
    task_id: str
    topic: str
    task_dir: str
    created_at: str
    workflow_version: str
    taxonomy_version: str
    confirmations: dict[str, Any] = Field(default_factory=dict)
    scenario_statuses: dict[str, ScenarioStatus] = Field(default_factory=dict)
