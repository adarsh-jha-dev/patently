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


# Distinct from "" (not answered): an unanswered form is incomplete, whereas
# "I don't know" is a complete answer a novice must be able to give. Both are
# dropped before the prompt is built.
UNSURE = "unsure"


class Rubric(BaseModel):
    """
    Structured framing collected alongside the free-text description. Every
    field changes the search: field/context set the terminology, kind decides
    whether elements decompose as steps or structure, and prior_approach
    supplies the angle the model is least able to guess.
    """

    # No "mechanism" field: the free-text description already carries it, and
    # asking twice trains people to paste the same paragraph into both.
    field: str = ""       # technical domain
    kind: str = ""        # method / apparatus / system / algorithm / composition
    components: str = ""  # key parts or steps
    io: str = ""          # what goes in, what comes out
    prior_approach: str = ""  # closest existing way this is done today
    novelty: str = ""     # what the applicant believes is new
    context: str = ""     # operating environment

    def answered(self) -> dict[str, str]:
        """Only the fields carrying real information."""
        return {
            k: v.strip()
            for k, v in self.model_dump().items()
            if v and v.strip() and v.strip() != UNSURE
        }

    def unsure(self) -> list[str]:
        return [
            k for k, v in self.model_dump().items()
            if (v or "").strip() == UNSURE
        ]


class AnalyzeRequest(BaseModel):
    description: str = Field(..., min_length=40, max_length=20000)
    top_k: Optional[int] = Field(None, ge=3, le=25)
    rubric: Optional[Rubric] = None


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
    # Set once the analysis has been persisted; None when DATABASE_URL is
    # unset, so the UI shows a share link only when there is something to link.
    slug: Optional[str] = None


class SavedSummary(BaseModel):
    slug: str
    created_at: str
    title: str
    label: str
    novelty_score: Optional[int] = None
    conclusive: bool
    corpus: str
    corpus_size: int
