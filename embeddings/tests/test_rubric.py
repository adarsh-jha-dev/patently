"""
Tests for the guided-form rubric.

What matters is what does NOT reach the prompt: a "not sure" field must be
indistinguishable from one the user never saw.

    cd embeddings && python -m pytest tests/ -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patently.analyze import RUBRIC_LABELS, render_rubric
from patently.schemas import UNSURE, Rubric


def test_no_rubric_renders_nothing():
    assert render_rubric(None) == ""


def test_empty_rubric_renders_nothing():
    assert render_rubric(Rubric()) == ""


def test_all_unsure_renders_nothing():
    """A novice who answers 'not sure' to everything still gets a clean run —
    the free-text description alone drives the analysis, unqualified."""
    everything_unknown = Rubric(**{k: UNSURE for k, _ in RUBRIC_LABELS})
    assert render_rubric(everything_unknown) == ""


def test_unsure_fields_are_absent_not_reported_as_unknown():
    out = render_rubric(Rubric(field="Optics and imaging", kind=UNSURE))
    assert "FIELD: Optics and imaging" in out
    assert "FORM" not in out
    # The sentinel itself must never reach the model in any casing.
    assert UNSURE not in out.lower()


def test_blank_and_whitespace_fields_are_dropped():
    out = render_rubric(Rubric(field="Software and computing", kind="   ", io=""))
    assert "FIELD" in out
    assert "FORM" not in out
    assert "INPUTS AND OUTPUTS" not in out


def test_substance_is_ordered_before_framing():
    """Mechanism and components qualify the invention; field and form only
    qualify the mechanism. The model should read them in that order."""
    out = render_rubric(
        Rubric(
            field="Energy and power",
            kind="Method or process",
            components="phase-change coolant channels; predictive pump controller",
            prior_approach="reactive thermostat control",
        )
    )
    body = out.splitlines()
    assert body[0] == "STRUCTURED FRAMING"
    positions = {line.split(":")[0]: i for i, line in enumerate(body)}
    assert positions["KEY PARTS OR STEPS"] < positions["CLOSEST EXISTING APPROACH"]
    assert positions["CLOSEST EXISTING APPROACH"] < positions["FIELD"]
    assert positions["FIELD"] < positions["FORM"]


def test_answered_and_unsure_partition_the_form():
    r = Rubric(
        field="Biotech and medical",
        kind=UNSURE,
        novelty="a thing that does a thing",
        components=UNSURE,
    )
    assert set(r.answered()) == {"field", "novelty"}
    assert set(r.unsure()) == {"kind", "components"}
    # Never both, and blanks belong to neither.
    assert not set(r.answered()) & set(r.unsure())
    assert "io" not in r.answered() and "io" not in r.unsure()


def test_every_rubric_field_has_a_heading():
    """A field added to the schema without a heading would silently never
    reach the prompt."""
    assert set(dict(RUBRIC_LABELS)) == set(Rubric().model_dump())
