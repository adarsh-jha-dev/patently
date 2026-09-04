"""
The analysis pipeline.

    decompose  (1 LLM call)  invention -> claim elements + search angles
    retrieve   (0 LLM calls) batch-embed angles, parallel search, RRF fuse
    assess     (1 LLM call)  element x reference coverage, with verbatim quotes
    synthesise (0 LLM calls) grounding check, whitespace, §103 combinations

Two LLM calls per analysis, total, regardless of how many candidates come
back. Everything that can be computed is computed rather than asked.
"""

from __future__ import annotations

import itertools
import re
from typing import Any, AsyncIterator, Callable

from . import config, prompts
from .llm import complete_json
from .retrieval import Embedder, Store, fuse
from .schemas import (
    AnalyzeResult,
    Combination,
    Element,
    ElementCoverage,
    ElementRisk,
    Query,
    Reference,
    Verdict,
)

# Weight of each coverage level when scoring how much of the invention a
# reference (or a combination) reads on.
LEVEL_WEIGHT = {"covered": 1.0, "partial": 0.5, "absent": 0.0}

# Matches a bare reference label (R1, R12) as a whole word.
_REF_TOKEN = re.compile(r"\bR\d{1,2}\b")

# An obviousness combination has to be argued — two references are only
# combinable with a reason. We discount combination risk relative to
# single-reference anticipation to reflect that.
COMBINATION_DISCOUNT = 0.85

# Below this, the best candidate the corpus could offer is not really on topic.
# The honest reading is then "this corpus has nothing in your field", which is
# a statement about the index, not about your invention.
MIN_CONCLUSIVE_RELEVANCE = 25


def _normalise(text: str) -> str:
    """Collapse whitespace and case so quote matching survives cosmetic drift."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _verify_quote(quote: str, abstract: str) -> bool:
    """
    Is `quote` genuinely a span of `abstract`?

    This is the guardrail that separates "cited evidence" from "plausible
    sentence the model wrote". A citation that cannot be located in the source
    is not evidence, so anything failing this check gets demoted rather than
    displayed as a finding.
    """
    q = _normalise(quote)
    if len(q) < 12:
        return False
    return q in _normalise(abstract)


async def _decompose(description: str) -> dict[str, Any]:
    data = await complete_json(
        system=prompts.DECOMPOSE_SYSTEM,
        user=f"Invention disclosure:\n\n{description.strip()}",
        schema=prompts.DECOMPOSE_SCHEMA,
        max_tokens=3000,
    )
    # Re-id defensively: the rest of the pipeline joins on these strings, and a
    # duplicate or missing id from the model would silently drop a row.
    elements = [
        Element(id=f"E{i + 1}", label=e.get("label", f"Element {i + 1}"), text=e.get("text", ""))
        for i, e in enumerate(data.get("elements", [])[:8])
    ]
    queries = [
        Query(id=f"Q{i + 1}", angle=q.get("angle", f"Angle {i + 1}"), text=q.get("text", ""))
        for i, q in enumerate(data.get("queries", [])[:6])
        if (q.get("text") or "").strip()
    ]
    return {
        "title": data.get("title") or "Untitled invention",
        "restatement": data.get("restatement") or "",
        "elements": elements,
        "queries": queries,
    }


async def _assess(
    elements: list[Element], candidates: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    element_block = "\n".join(f"{e.id} [{e.label}]: {e.text}" for e in elements)
    ref_block = "\n\n".join(
        f"### {c['ref_id']}\n{c['abstract'][: config.ASSESS_ABSTRACT_CHARS]}"
        for c in candidates
    )
    user = (
        f"CLAIM ELEMENTS\n{element_block}\n\n"
        f"CANDIDATE REFERENCES\n{ref_block}\n\n"
        f"Assess all {len(candidates)} references against all "
        f"{len(elements)} elements."
    )
    data = await complete_json(
        system=prompts.ASSESS_SYSTEM,
        user=user,
        schema=prompts.ASSESS_SCHEMA,
        max_tokens=8000,
    )
    return {a.get("ref_id"): a for a in data.get("assessments", []) if a.get("ref_id")}


def _build_references(
    candidates: list[dict[str, Any]],
    assessments: dict[str, dict[str, Any]],
    elements: list[Element],
) -> tuple[list[Reference], int]:
    """Merge retrieval hits with the assessment pass, applying the quote check."""
    valid_ids = {e.id for e in elements}
    order = {e.id: i for i, e in enumerate(elements)}
    refs: list[Reference] = []
    demoted = 0

    for cand in candidates:
        a = assessments.get(cand["ref_id"], {})
        seen: set[str] = set()
        coverage: list[ElementCoverage] = []

        for item in a.get("coverage", []):
            eid = item.get("element_id")
            if eid not in valid_ids or eid in seen:
                continue
            seen.add(eid)
            level = item.get("level", "absent")
            quote = (item.get("quote") or "").strip()
            verified = True

            if level in ("covered", "partial"):
                verified = _verify_quote(quote, cand["abstract"])
                if not verified:
                    demoted += 1
                    # An unverifiable citation cannot support the stronger
                    # finding. Demote one step rather than discard, so the
                    # signal survives but never drives a "covered" verdict.
                    level = "partial" if level == "covered" else "absent"
                    if level == "absent":
                        quote = ""

            coverage.append(
                ElementCoverage(
                    element_id=eid, level=level, quote=quote, quote_verified=verified
                )
            )

        # Any element the model skipped is absent, not missing — the matrix
        # must be complete or the coverage arithmetic is wrong.
        for e in elements:
            if e.id not in seen:
                coverage.append(ElementCoverage(element_id=e.id, level="absent"))

        coverage.sort(key=lambda c: order.get(c.element_id, 99))
        refs.append(
            Reference(
                ref_id=cand["ref_id"],
                patent_id=cand["patent_id"],
                title=cand["title"],
                abstract=cand["abstract"],
                score=round(cand["best_score"], 4),
                found_by=cand["found_by"],
                relevance=int(a.get("relevance", 0) or 0),
                note=a.get("note", ""),
                coverage=coverage,
            )
        )

    # Renumber after ranking so the labels read R1..Rn in display order. The
    # retrieval-order ids were only ever a join key between the assess prompt
    # and its response, and that join is done by this point; everything
    # downstream (combinations, the UI matrix) uses these final ids.
    refs.sort(key=lambda r: r.relevance, reverse=True)
    remap = {r.ref_id: f"R{i + 1}" for i, r in enumerate(refs)}
    for r in refs:
        # The model sometimes writes a reference id into its own note. Those
        # ids are pre-sort, so rewrite them here or the note will cite a
        # neighbour's label — remapping in one pass so a renamed id can't be
        # renamed a second time.
        if r.note:
            r.note = _REF_TOKEN.sub(
                lambda m: remap.get(m.group(0), m.group(0)), r.note
            )
        r.ref_id = remap[r.ref_id]
    return refs, demoted


def _coverage_map(ref: Reference) -> dict[str, float]:
    return {c.element_id: LEVEL_WEIGHT[c.level] for c in ref.coverage}


def _element_risk(refs: list[Reference], elements: list[Element]) -> list[ElementRisk]:
    risks: list[ElementRisk] = []
    for e in elements:
        covered = [r.ref_id for r in refs for c in r.coverage
                   if c.element_id == e.id and c.level == "covered"]
        partial = [r.ref_id for r in refs for c in r.coverage
                   if c.element_id == e.id and c.level == "partial"]
        level = "covered" if covered else ("partial" if partial else "absent")
        risks.append(
            ElementRisk(
                element_id=e.id, level=level, covered_by=covered, partial_by=partial
            )
        )
    return risks


def _combinations(
    refs: list[Reference], elements: list[Element], limit: int = 3
) -> list[Combination]:
    """
    Find pairs of references that together read on more of the invention than
    either does alone — the shape of a §103 obviousness rejection.

    Exhaustive over pairs of the top references, which is what makes it exact
    rather than a guess: with ~12 candidates that is 66 pairs of cheap set
    arithmetic. No LLM call is involved in finding these, which is why the
    result is reproducible.
    """
    pool = refs[:12]
    if len(pool) < 2 or not elements:
        return []

    maps = {r.ref_id: _coverage_map(r) for r in pool}
    n = len(elements)
    best_single = max(
        (sum(maps[r.ref_id].get(e.id, 0.0) for e in elements) / n for r in pool),
        default=0.0,
    )

    scored: list[tuple[float, Combination]] = []
    for a, b in itertools.combinations(pool, 2):
        ma, mb = maps[a.ref_id], maps[b.ref_id]
        per_element = {e.id: max(ma.get(e.id, 0.0), mb.get(e.id, 0.0)) for e in elements}
        fraction = sum(per_element.values()) / n
        # Only interesting if the pair genuinely beats the best single
        # reference — otherwise it is not a combination argument, it is one
        # reference with a passenger.
        if fraction <= best_single + 1e-9:
            continue
        scored.append((
            fraction,
            Combination(
                ref_ids=[a.ref_id, b.ref_id],
                covers=[eid for eid, v in per_element.items() if v >= 1.0],
                missing=[eid for eid, v in per_element.items() if v <= 0.0],
                coverage_fraction=round(fraction, 3),
            ),
        ))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [c for _, c in scored[:limit]]


def _verdict(
    refs: list[Reference],
    elements: list[Element],
    combos: list[Combination],
    whitespace: list[str],
) -> Verdict:
    n = len(elements) or 1
    anticipation = max(
        (sum(_coverage_map(r).get(e.id, 0.0) for e in elements) / n for r in refs),
        default=0.0,
    )
    combination = max((c.coverage_fraction for c in combos), default=0.0)
    exposure = max(anticipation, COMBINATION_DISCOUNT * combination)
    score = int(round(100 * (1 - exposure)))

    top_relevance = max((r.relevance for r in refs), default=0)
    conclusive = bool(refs) and top_relevance >= MIN_CONCLUSIVE_RELEVANCE

    if not conclusive:
        # Reporting "open field" here would be the single most damaging thing
        # this tool could do: it reads as a novelty clearance when it actually
        # means the search came back empty.
        reason = (
            "nothing was retrieved"
            if not refs
            else f"the closest match scored only {top_relevance}/100 for relevance"
        )
        return Verdict(
            novelty_score=score,
            label="Inconclusive",
            anticipation_risk=round(anticipation, 3),
            combination_risk=round(combination, 3),
            conclusive=False,
            top_relevance=top_relevance,
            summary=(
                f"The indexed corpus holds nothing close to this invention — "
                f"{reason}. That is a fact about the index, not about your "
                "novelty. Index more of the corpus, or a corpus covering this "
                "field, before reading anything into a clean result."
            ),
        )

    if score >= 70:
        label = "Open field"
        summary = (
            f"No reference in the indexed corpus reads on more than "
            f"{anticipation:.0%} of the invention."
        )
    elif score >= 40:
        label = "Contested"
        summary = (
            f"The closest single reference reads on {anticipation:.0%} of the "
            f"invention; the strongest two-reference combination reaches "
            f"{combination:.0%}."
        )
    else:
        label = "Crowded"
        summary = (
            f"Prior art reads on most of the invention as described "
            f"({anticipation:.0%} from a single reference, {combination:.0%} in "
            "combination). Novelty likely needs to be argued more narrowly."
        )

    if whitespace:
        names = ", ".join(whitespace)
        summary += f" Nothing found teaches {names}."

    return Verdict(
        novelty_score=score,
        label=label,
        anticipation_risk=round(anticipation, 3),
        combination_risk=round(combination, 3),
        conclusive=True,
        top_relevance=top_relevance,
        summary=summary,
    )


async def run_analysis(
    description: str,
    embedder: Embedder,
    store: Store,
    top_k: int | None = None,
    on_progress: Callable[[str, dict], Any] | None = None,
) -> AnalyzeResult:
    """Run the full pipeline. `on_progress(stage, payload)` is awaited if given."""
    top_k = top_k or config.ASSESS_TOP_K

    async def emit(stage: str, payload: dict) -> None:
        if on_progress is not None:
            await on_progress(stage, payload)

    await emit("decompose", {"message": "Decomposing invention into claim elements"})
    plan = await _decompose(description)
    elements: list[Element] = plan["elements"]
    queries: list[Query] = plan["queries"]
    if not queries:
        raise ValueError("decomposition produced no search queries")

    await emit(
        "plan",
        {
            "title": plan["title"],
            "restatement": plan["restatement"],
            "elements": [e.model_dump() for e in elements],
            "queries": [q.model_dump() for q in queries],
        },
    )

    await emit("retrieve", {"message": f"Searching {len(queries)} angles in parallel"})
    # One encode call for every angle — batching beats N sequential encodes.
    vectors = embedder.encode([q.text for q in queries])
    result_sets = await store.search_many(vectors, config.RETRIEVE_PER_QUERY)
    fused = fuse(result_sets, [q.id for q in queries])

    candidates = fused[:top_k]
    for i, c in enumerate(candidates):
        c["ref_id"] = f"R{i + 1}"

    await emit(
        "retrieved",
        {
            "candidates": len(candidates),
            "pool": len(fused),
            "message": f"{len(fused)} unique patents found, assessing top {len(candidates)}",
        },
    )

    if not candidates:
        empty = _verdict([], elements, [], [e.id for e in elements])
        return AnalyzeResult(
            title=plan["title"],
            restatement=plan["restatement"],
            elements=elements,
            queries=queries,
            references=[],
            element_risk=_element_risk([], elements),
            whitespace=[e.id for e in elements],
            combinations=[],
            verdict=empty,
            stats={"llm_calls": 1, "pool": 0},
        )

    await emit("assess", {"message": "Mapping elements against each reference"})
    assessments = await _assess(elements, candidates)
    refs, demoted = _build_references(candidates, assessments, elements)

    risk = _element_risk(refs, elements)
    whitespace = [r.element_id for r in risk if r.level == "absent"]
    combos = _combinations(refs, elements)
    verdict = _verdict(refs, elements, combos, whitespace)

    return AnalyzeResult(
        title=plan["title"],
        restatement=plan["restatement"],
        elements=elements,
        queries=queries,
        references=refs,
        element_risk=risk,
        whitespace=whitespace,
        combinations=combos,
        verdict=verdict,
        stats={
            "llm_calls": 2,
            "pool": len(fused),
            "assessed": len(candidates),
            "quotes_demoted": demoted,
        },
    )
