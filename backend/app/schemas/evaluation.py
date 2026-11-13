"""Evaluation API schemas (L3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DatasetItem(BaseModel):
    """One benchmark pair. retrieval kind: query + expected doc ids.
    generation kind (N3): query (+ optional reference answer) — expected ids optional.
    """

    query: str = Field(min_length=1, max_length=512)
    expected_doc_ids: list[str] = Field(default_factory=list, max_length=20)
    reference_answer: str | None = Field(default=None, max_length=2000)


class EvaluationCreateRequest(BaseModel):
    """``POST /evaluations`` body — a named dataset benchmarked immediately."""

    name: str = Field(min_length=1, max_length=128)
    top_k: int = Field(default=5, ge=1, le=20)
    dataset: list[DatasetItem] = Field(min_length=1, max_length=100)
    #: Optional rerun lineage (L4.1): the run this one was derived from.
    parent_run_id: str | None = None
    #: Retrieval mode under test (N2 ablation).
    retrieval_mode: str = Field(
        default="dense", pattern=r"^(dense|hybrid|hybrid_rerank)$"
    )
    #: Evaluation dimension (N3): retrieval metrics or generation quality.
    kind: str = Field(default="retrieval", pattern=r"^(retrieval|generation)$")

    @model_validator(mode="after")
    def _validate_by_kind(self) -> EvaluationCreateRequest:
        if not any(item.query.strip() for item in self.dataset):
            raise ValueError("dataset must contain at least one non-blank query")
        if self.kind == "retrieval" and any(
            not item.expected_doc_ids for item in self.dataset
        ):
            raise ValueError("retrieval kind requires expected_doc_ids on every item")
        return self


class EvaluationRunOut(BaseModel):
    """Full run: input dataset + aggregate metrics + per-query breakdown."""

    id: str
    name: str
    parent_run_id: str | None = None
    retrieval_mode: str = "dense"
    kind: str = "retrieval"
    dataset: list[dict[str, Any]]
    metrics: dict[str, Any] | None = None
    result: list[dict[str, Any]] | None = None
    created_at: datetime | None = None


class ReviewRequest(BaseModel):
    """``PATCH /evaluations/{id}/results/{i}`` body — human verdict on a row."""

    verdict: str = Field(pattern=r"^(correct|false_positive|missed)$")
    note: str | None = Field(default=None, max_length=512)


class EvaluationSummary(BaseModel):
    """History row: identity + metrics only (dataset/result on the detail)."""

    id: str
    name: str
    parent_run_id: str | None = None
    retrieval_mode: str = "dense"
    kind: str = "retrieval"
    queries: int | None = None
    metrics: dict[str, Any] | None = None
    created_at: datetime | None = None
