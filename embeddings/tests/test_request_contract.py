"""
The wire contract between the web form and the analysis request.

The rubric's field names exist in two places — `web/lib/rubric.ts` builds the
JSON and `patently.schemas.Rubric` parses it — and pydantic ignores keys it
does not recognise. A renamed field on either side would therefore not raise
anything: the value would simply stop reaching the prompt, and the analysis
would quietly get worse with no error anywhere. These tests fail loudly
instead.

    cd embeddings && python -m pytest tests/ -q
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patently.analyze import render_rubric
from patently.schemas import UNSURE, AnalyzeRequest, Rubric

RUBRIC_TS = Path(__file__).resolve().parents[2] / "web" / "lib" / "rubric.ts"

DESCRIPTION = (
    "A battery pack thermal management system that routes coolant through "
    "phase-change material channels between cells."
)

# Exactly the body web/app/page.tsx sends, including "unsure" for the two
# questions a first-time inventor is most likely to stall on.
FORM_BODY = {
    "description": DESCRIPTION,
    "rubric": {
        "field": "Energy, power and storage",
        "kind": "System or architecture",
        "components": "phase-change channels; a pump; a predictive controller",
        "io": UNSURE,
        "prior_approach": "reactive thermostat control",
        "novelty": UNSURE,
        "context": "Vehicle or mobile platform",
    },
}


def test_form_body_parses():
    req = AnalyzeRequest(**FORM_BODY)
    assert req.rubric is not None
    assert req.rubric.field == "Energy, power and storage"
    assert set(req.rubric.answered()) == {
        "field",
        "kind",
        "components",
        "prior_approach",
        "context",
    }
    assert set(req.rubric.unsure()) == {"io", "novelty"}


def test_unsure_answers_never_reach_the_prompt():
    req = AnalyzeRequest(**FORM_BODY)
    rendered = render_rubric(req.rubric)
    assert "CLOSEST EXISTING APPROACH: reactive thermostat control" in rendered
    assert "INPUTS AND OUTPUTS" not in rendered
    assert "CLAIMED NOVELTY" not in rendered


def test_rubric_is_optional():
    """The plain free-text path has to keep working untouched."""
    req = AnalyzeRequest(description=DESCRIPTION)
    assert req.rubric is None
    assert render_rubric(req.rubric) == ""


def test_typescript_and_python_agree_on_field_names():
    """
    The RubricId union in rubric.ts must match Rubric's fields exactly.

    Parsed out of the source rather than duplicated here, so this test tracks
    the real declaration instead of a copy that can drift alongside it.
    """
    source = RUBRIC_TS.read_text()
    union = re.search(r"export type RubricId =(.*?);", source, re.S)
    assert union, "could not find the RubricId union in rubric.ts"
    ts_fields = set(re.findall(r'"([a-z_]+)"', union.group(1)))
    assert ts_fields == set(Rubric().model_dump()), (
        f"rubric.ts declares {sorted(ts_fields)} but "
        f"schemas.Rubric declares {sorted(Rubric().model_dump())}"
    )


def test_typescript_unsure_sentinel_matches_python():
    source = RUBRIC_TS.read_text()
    match = re.search(r'export const UNSURE = "([^"]+)"', source)
    assert match, "could not find the UNSURE sentinel in rubric.ts"
    assert match.group(1) == UNSURE


@pytest.mark.parametrize("bad", ["", "too short"])
def test_description_minimum_is_enforced(bad):
    """The form gates on this client-side; the API must not rely on that."""
    with pytest.raises(Exception):
        AnalyzeRequest(description=bad, rubric=FORM_BODY["rubric"])


def test_body_is_json_serialisable_as_sent():
    """Guards against a non-serialisable value creeping into the fixture."""
    assert json.loads(json.dumps(FORM_BODY)) == FORM_BODY
