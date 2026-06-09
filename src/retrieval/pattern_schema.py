"""
pattern_schema.py — Pydantic V2 schema for the Pattern Library (v1.2).

Authoritative reference: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 2.3.

Model hierarchy:
    CrossLingualTestQuery
    RouteConfig
    DeletionProposal
    LifecycleEvent
    Lifecycle
    Origin
    Pattern  (top-level)

Validation invariants:
    - Pattern.id matches r"^pat_[a-z_]+_\\d{3}$"
    - Pattern.examples: 5..15 entries
    - Pattern.cross_lingual_test_queries: at least 2 ja + 2 zh
    - Pattern.priority: 0..1000
    - CrossLingualTestQuery.min_cosine: 0.0..1.0 if set
    - Lifecycle.last_xling_pass_rate: 0.0..1.0 if set
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class CrossLingualTestQuery(BaseModel):
    lang: Literal["ja", "zh", "en", "ko", "es", "fr", "de", "pt"]
    query: str
    expected_match: bool
    min_cosine: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RouteConfig(BaseModel):
    primary_box: Literal[
        "box_0", "box_1", "box_2", "box_3", "box_4",
        "box_5", "box_6", "box_7", "box_w",
    ]
    exclude_boxes: list[str] = Field(default_factory=list)
    synthesis_mode: str


class DeletionProposal(BaseModel):
    proposal_id: str
    proposer: str
    date: datetime
    reason: str
    status: Literal["pending", "approved", "rejected"]
    resolution_date: Optional[datetime] = None
    resolution_note: Optional[str] = None


class LifecycleEvent(BaseModel):
    timestamp: datetime
    event: Literal[
        "created",
        "updated",
        "deletion_proposed",
        "approved_for_deletion",
        "rejected_deletion",
        "deprecated",
        "archived",
        "xling_pass_rate_drop",
        "audit_flag",
    ]
    actor: str
    detail: str


class Lifecycle(BaseModel):
    hit_count: int = 0
    last_hit_date: Optional[datetime] = None
    last_xling_pass_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    audit_status: Literal[
        "active",
        "deprecation_candidate",
        "user_deletion_proposed",
        "under_review",
        "deprecated",
    ] = "active"
    deletion_proposals: list[DeletionProposal] = Field(default_factory=list)
    history: list[LifecycleEvent] = Field(default_factory=list)


class Origin(BaseModel):
    type: Literal["forensic", "manual", "autogen", "secretary"]
    evolution_log_entry: Optional[int] = None
    date: datetime
    scenario_id: Optional[str] = None
    batch_id: Optional[str] = None
    groq_run_id: Optional[str] = None
    prompt_version: Optional[str] = None


class Pattern(BaseModel):
    id: str = Field(pattern=r"^pat_[a-z_]+_\d{3}$")
    version: str = "1.0"
    lang: Literal["en"] = "en"
    topic: str
    # Phase 4 v2 Commit 3: sub_topic gives per-sub-topic granularity
    # under the 5 mandatory-invariant topics. Empty string means
    # "topic-level only" (Phase 1-3 patterns before migration). New
    # patterns generated in Phase 4 must specify sub_topic.
    sub_topic: str = ""
    intent: str
    concepts: list[str] = Field(default_factory=list)
    priority: int = Field(default=100, ge=0, le=1000)
    examples: list[str] = Field(min_length=5, max_length=15)
    negative_examples: list[str] = Field(default_factory=list)
    context_required: Optional[dict] = None
    context_excluded: list[str] = Field(default_factory=list)
    route: RouteConfig
    tags: list[str] = Field(default_factory=list)
    cross_lingual_test_queries: list[CrossLingualTestQuery] = Field(min_length=4)
    lifecycle: Lifecycle = Field(default_factory=Lifecycle)
    origin: Origin
    deprecated: bool = False

    @field_validator("cross_lingual_test_queries")
    @classmethod
    def must_have_ja_and_zh(
        cls, v: list[CrossLingualTestQuery]
    ) -> list[CrossLingualTestQuery]:
        langs = [q.lang for q in v]
        if langs.count("ja") < 2 or langs.count("zh") < 2:
            raise ValueError(
                "cross_lingual_test_queries must include at least 2 ja and 2 zh queries"
            )
        return v
