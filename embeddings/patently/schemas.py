"""Wire types for the API. These are what the web app renders."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

CoverageLevel = Literal["covered", "partial", "absent"]


# ---- retrieval -------------------------------------------------------------


class SearchHit(BaseModel):
    patent_id: str
    title: Optional[str] = None
    abstract: Optional[str] = None
    score: float


class SearchResponse(BaseModel):
    hits: list[SearchHit]


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=128)


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    dim: int
    device: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(10, ge=1, le=100)


# ---- analysis --------------------------------------------------------------


class Element(BaseModel):
    """One discrete technical feature of the invention — a claim element."""

    id: str
    label: str
    text: str


class Query(BaseModel):
    """One search angle. Multiple angles is the point: a single embedding of a
    long description averages away the specifics that actually matter."""

    id: str
    angle: str
    text: str


class ElementCoverage(BaseModel):
    element_id: str
    level: CoverageLevel
    quote: str = ""
    # False when the model's quote could not be found verbatim in the source
    # abstract. Unverified `covered` claims are demoted to `partial` before
    # this is returned — see analyze.py.
    quote_verified: bool = True


class Reference(BaseModel):
    ref_id: str
    patent_id: str
    title: str
    abstract: str
    score: float
    found_by: list[str]  # query ids that surfaced this reference
    relevance: int = 0  # 0-100, from the assessment pass
    note: str = ""
    coverage: list[ElementCoverage] = []


class ElementRisk(BaseModel):
    element_id: str
    level: CoverageLevel
    covered_by: list[str] = []  # ref_ids at level "covered"
    partial_by: list[str] = []  # ref_ids at level "partial"


class Combination(BaseModel):
    """A §103-shaped result: two references that between them read on more of
    the invention than either does alone."""

    ref_ids: list[str]
    covers: list[str]
    missing: list[str]
    coverage_fraction: float


class Verdict(BaseModel):
    novelty_score: int  # 0-100, higher = more whitespace left
    label: str
    anticipation_risk: float  # best single-reference coverage, 0-1
    combination_risk: float  # best two-reference coverage, 0-1
    summary: str
    # True when retrieval returned nothing topically close. A clean result
    # against a corpus that holds nothing in the field is an absence of
    # evidence, not evidence of novelty, and must not be reported as one.
    conclusive: bool = True
    top_relevance: int = 0


class AnalyzeRequest(BaseModel):
    description: str = Field(..., min_length=40, max_length=20000)
    top_k: Optional[int] = Field(None, ge=3, le=25)


class AnalyzeResult(BaseModel):
    title: str
    restatement: str
    elements: list[Element]
    queries: list[Query]
    references: list[Reference]
    element_risk: list[ElementRisk]
    whitespace: list[str]  # element ids nothing in the corpus covers
    combinations: list[Combination]
    verdict: Verdict
    stats: dict = {}
