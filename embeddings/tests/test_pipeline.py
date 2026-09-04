"""
Tests for the deterministic half of the pipeline.

Everything here runs without a network, a model, or an API key — which is the
point: the parts that decide what the user is told (grounding, fusion, the
§103 arithmetic, the inconclusive guard) are pure functions, and they are
where a silent regression would do real damage.

    cd embeddings && python -m pytest tests/ -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patently import analyze as A
from patently.retrieval import fuse, stable_point_id
from patently.schemas import Element, ElementCoverage, Reference


def make_elements(n=3):
    return [Element(id=f"E{i}", label=f"Feature {i}", text=f"text {i}") for i in range(1, n + 1)]


def make_ref(ref_id, levels, relevance=80, abstract="", elements=None):
    elements = elements or make_elements(len(levels))
    return Reference(
        ref_id=ref_id,
        patent_id=ref_id,
        title="",
        abstract=abstract,
        score=0.5,
        found_by=["Q1"],
        relevance=relevance,
        coverage=[
            ElementCoverage(element_id=e.id, level=l) for e, l in zip(elements, levels)
        ],
    )


# ---- point ids -------------------------------------------------------------


def test_point_id_is_stable_across_calls():
    assert stable_point_id("bp-g-7") == stable_point_id("bp-g-7")


def test_point_id_fits_in_signed_64_bit():
    # Qdrant rejects ids outside the u64 range; the >> 1 keeps headroom.
    assert 0 <= stable_point_id("bp-g-999999") < 2**63


def test_point_id_differs_per_key():
    assert stable_point_id("bp-g-1") != stable_point_id("bp-g-2")


# ---- fusion ----------------------------------------------------------------


def test_rrf_prefers_documents_found_by_multiple_angles():
    """The whole reason for multi-angle search: broad relevance beats one
    lexical coincidence, even when the single-angle hit scores higher."""
    hit = lambda pid, s: {"patent_id": pid, "title": "", "abstract": "", "score": s}
    a = [hit("P1", 0.99), hit("P2", 0.70)]
    b = [hit("P3", 0.98), hit("P2", 0.65)]
    ranked = fuse([a, b], ["Q1", "Q2"])
    assert ranked[0]["patent_id"] == "P2"
    assert ranked[0]["found_by"] == ["Q1", "Q2"]


def test_fuse_records_best_score_not_last_score():
    hit = lambda pid, s: {"patent_id": pid, "title": "", "abstract": "", "score": s}
    ranked = fuse([[hit("P1", 0.9)], [hit("P1", 0.3)]], ["Q1", "Q2"])
    assert ranked[0]["best_score"] == 0.9


# ---- quote grounding -------------------------------------------------------

ABSTRACT = "A neural network accelerator uses a systolic array to perform matrix multiplication."


@pytest.mark.parametrize(
    "quote,expected",
    [
        ("uses a systolic array to perform", True),
        ("USES   a  SYSTOLIC array to perform", True),  # whitespace/case tolerant
        ("uses a quantum array to perform", False),  # fabricated
        ("array", False),  # too short to be evidence
        ("", False),
    ],
)
def test_quote_verification(quote, expected):
    assert A._verify_quote(quote, ABSTRACT) is expected


def test_unverified_covered_finding_is_demoted_to_partial():
    """An unlocatable citation is not evidence, so it must never carry a
    'covered' finding into the coverage map or the §103 arithmetic."""
    elements = make_elements(1)
    candidates = [{
        "ref_id": "R1", "patent_id": "p1", "title": "", "abstract": ABSTRACT,
        "best_score": 0.9, "found_by": ["Q1"],
    }]
    assessments = {"R1": {
        "ref_id": "R1", "relevance": 90, "note": "",
        "coverage": [{"element_id": "E1", "level": "covered",
                      "quote": "uses a quantum annealer to perform"}],
    }}
    refs, demoted = A._build_references(candidates, assessments, elements)
    assert demoted == 1
    assert refs[0].coverage[0].level == "partial"
    assert refs[0].coverage[0].quote_verified is False


def test_verified_quote_survives_intact():
    elements = make_elements(1)
    candidates = [{
        "ref_id": "R1", "patent_id": "p1", "title": "", "abstract": ABSTRACT,
        "best_score": 0.9, "found_by": ["Q1"],
    }]
    assessments = {"R1": {
        "ref_id": "R1", "relevance": 90, "note": "",
        "coverage": [{"element_id": "E1", "level": "covered",
                      "quote": "uses a systolic array to perform"}],
    }}
    refs, demoted = A._build_references(candidates, assessments, elements)
    assert demoted == 0
    assert refs[0].coverage[0].level == "covered"


def test_elements_omitted_by_the_model_default_to_absent():
    """The matrix must be complete — a missing row would silently skew every
    coverage fraction computed from it."""
    elements = make_elements(3)
    candidates = [{
        "ref_id": "R1", "patent_id": "p1", "title": "", "abstract": ABSTRACT,
        "best_score": 0.9, "found_by": ["Q1"],
    }]
    assessments = {"R1": {"ref_id": "R1", "relevance": 50, "note": "", "coverage": []}}
    refs, _ = A._build_references(candidates, assessments, elements)
    assert len(refs[0].coverage) == 3
    assert all(c.level == "absent" for c in refs[0].coverage)


# ---- §103 combinations -----------------------------------------------------


def test_finds_the_pair_that_together_covers_everything():
    elements = make_elements(3)
    refs = [
        make_ref("R1", ["covered", "covered", "absent"], elements=elements),
        make_ref("R2", ["absent", "absent", "covered"], elements=elements),
    ]
    combos = A._combinations(refs, elements)
    assert combos[0].ref_ids == ["R1", "R2"]
    assert combos[0].coverage_fraction == 1.0
    assert combos[0].missing == []


def test_pair_that_adds_nothing_is_not_reported():
    """Not a combination argument — one reference with a passenger."""
    elements = make_elements(3)
    refs = [
        make_ref("R1", ["covered", "covered", "covered"], elements=elements),
        make_ref("R2", ["covered", "absent", "absent"], elements=elements),
    ]
    assert A._combinations(refs, elements) == []


# ---- verdict ---------------------------------------------------------------


def test_low_relevance_results_are_reported_as_inconclusive():
    """The dangerous failure mode: an empty corpus reading as a clearance."""
    elements = make_elements(3)
    refs = [make_ref("R1", ["absent"] * 3, relevance=4, elements=elements)]
    v = A._verdict(refs, elements, [], [e.id for e in elements])
    assert v.conclusive is False
    assert v.label == "Inconclusive"
    assert "not about your" in v.summary


def test_empty_results_are_inconclusive_not_open_field():
    elements = make_elements(3)
    v = A._verdict([], elements, [], [e.id for e in elements])
    assert v.conclusive is False


def test_genuinely_clear_result_is_open_field():
    elements = make_elements(3)
    refs = [make_ref("R1", ["absent"] * 3, relevance=70, elements=elements)]
    v = A._verdict(refs, elements, [], [e.id for e in elements])
    assert v.conclusive is True
    assert v.label == "Open field"
    assert v.novelty_score == 100


def test_full_anticipation_scores_zero():
    elements = make_elements(3)
    refs = [make_ref("R1", ["covered"] * 3, relevance=95, elements=elements)]
    v = A._verdict(refs, elements, [], [])
    assert v.novelty_score == 0
    assert v.label == "Crowded"
    assert v.anticipation_risk == 1.0


def test_combination_risk_is_discounted_below_anticipation():
    """Two references only combine with an argument, so a 100% combination
    must not score as harshly as a 100% single-reference anticipation."""
    elements = make_elements(2)
    refs = [
        make_ref("R1", ["covered", "absent"], relevance=90, elements=elements),
        make_ref("R2", ["absent", "covered"], relevance=90, elements=elements),
    ]
    combos = A._combinations(refs, elements)
    v = A._verdict(refs, elements, combos, [])
    assert v.combination_risk == 1.0
    assert v.anticipation_risk == 0.5
    assert v.novelty_score == 15  # 100 * (1 - 0.85)


def test_reference_ids_are_renumbered_into_display_order():
    """Columns should read R1..Rn most-relevant-first, and a note that cites a
    pre-sort id must be rewritten to match — otherwise a card labelled R1
    carries prose describing some other reference."""
    elements = make_elements(1)
    candidates = [
        {"ref_id": f"R{i}", "patent_id": f"p{i}", "title": "", "abstract": "x" * 50,
         "best_score": 0.5, "found_by": ["Q1"]}
        for i in (1, 2, 3)
    ]
    assessments = {
        "R1": {"ref_id": "R1", "relevance": 10, "note": "R1 caches, unlike R3.", "coverage": []},
        "R2": {"ref_id": "R2", "relevance": 5, "note": "R2 is unrelated.", "coverage": []},
        "R3": {"ref_id": "R3", "relevance": 90, "note": "R3 teaches auctions.", "coverage": []},
    }
    refs, _ = A._build_references(candidates, assessments, elements)

    assert [r.ref_id for r in refs] == ["R1", "R2", "R3"]
    assert [r.patent_id for r in refs] == ["p3", "p1", "p2"]
    assert refs[0].note == "R1 teaches auctions."
    assert refs[1].note == "R2 caches, unlike R1."  # both ids follow the rename


# ---- provider payloads -----------------------------------------------------
#
# The OpenAI path can't be exercised against the live API from CI, so its two
# real failure modes are pinned here instead: a schema that strict mode
# rejects, and a request built with parameters the model family refuses.

from patently import llm, prompts  # noqa: E402


def walk_objects(schema, path="$"):
    """Yield every JSON-Schema object node, with a path for error messages."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield path, schema
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                for name, sub in value.items():
                    yield from walk_objects(sub, f"{path}.{name}")
            elif key == "items":
                yield from walk_objects(value, f"{path}[]")


@pytest.mark.parametrize(
    "name,schema",
    [("decompose", prompts.DECOMPOSE_SCHEMA), ("assess", prompts.ASSESS_SCHEMA)],
)
def test_schemas_satisfy_openai_strict_mode(name, schema):
    """strict:true requires additionalProperties:false on every object and
    every declared property listed in `required` — violating either returns a
    400 at request time, not a warning."""
    for path, node in walk_objects(schema):
        assert node.get("additionalProperties") is False, (
            f"{name}{path}: strict mode needs additionalProperties: false"
        )
        props = set(node.get("properties", {}))
        required = set(node.get("required", []))
        assert props == required, (
            f"{name}{path}: strict mode needs every property required; "
            f"missing {sorted(props - required)}"
        )


@pytest.mark.parametrize(
    "name,schema",
    [("decompose", prompts.DECOMPOSE_SCHEMA), ("assess", prompts.ASSESS_SCHEMA)],
)
def test_gemini_schema_conversion_strips_every_unsupported_keyword(name, schema):
    """Gemini rejects the keywords OpenAI strict mode requires, so the same
    authored schema has to survive a down-conversion at every nesting level."""
    import json

    converted = json.dumps(llm._to_gemini_schema(schema))
    for banned in ("additionalProperties", "$schema", "strict"):
        assert banned not in converted, f"{name}: {banned} leaked into Gemini schema"
    # The conversion must not lose the structure it is supposed to preserve.
    assert '"properties"' in converted and '"required"' in converted


def test_openai_payload_uses_modern_token_parameter_by_default():
    llm._OPENAI_QUIRKS.clear()
    payload = llm._openai_payload("s", "u", {"type": "object"}, 4096)
    assert payload["max_completion_tokens"] == 4096
    assert "max_tokens" not in payload  # deprecated; rejected by reasoning models
    assert payload["temperature"] == 0.1
    assert payload["response_format"]["json_schema"]["strict"] is True


def test_openai_payload_adapts_after_the_api_rejects_a_parameter():
    """A model family we can't identify from its id should cost one 400, not a
    permanently broken provider."""
    llm._OPENAI_QUIRKS.clear()
    assert llm._learn_openai_quirk(
        "Unsupported value: 'temperature' does not support 0.1 with this model."
    )
    payload = llm._openai_payload("s", "u", {"type": "object"}, 4096)
    assert "temperature" not in payload

    assert llm._learn_openai_quirk("Unrecognized request argument: max_completion_tokens")
    payload = llm._openai_payload("s", "u", {"type": "object"}, 4096)
    assert payload["max_tokens"] == 4096
    assert "max_completion_tokens" not in payload
    llm._OPENAI_QUIRKS.clear()


def test_unknown_rejection_does_not_trigger_an_endless_retry():
    llm._OPENAI_QUIRKS.clear()
    assert llm._learn_openai_quirk("You exceeded your current quota") is False
