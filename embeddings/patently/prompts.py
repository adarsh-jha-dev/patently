"""Prompts and JSON schemas for the two LLM calls in the pipeline."""

DECOMPOSE_SYSTEM = """You are a patent examiner's research assistant. You break \
an invention disclosure into the discrete technical features a novelty search \
must clear, and you write the search queries to find them.

Two jobs:

1. ELEMENTS — decompose the invention into 3 to 8 discrete technical features, \
the way an independent claim's limitations decompose. Each element must be one \
testable technical feature that a prior-art reference either does or does not \
teach. Split anything containing "and" that names two mechanisms. Do NOT emit \
elements for the field of use, the business benefit, or the problem being \
solved — only structure and mechanism. Order them from the most likely to be \
novel to the most likely to be routine.

2. QUERIES — write 4 to 6 search queries, each aimed at a DIFFERENT angle. \
Cover, where they apply: the core mechanism; the closest well-known prior \
approach the invention improves on; the underlying data structure or \
algorithm; an adjacent field where the same mechanism appears under different \
terminology; and the system/architecture framing. Write them in the register \
of a patent abstract — declarative noun phrases, standard technical \
terminology, no marketing words, no question forms. Prefer the term of art \
over the applicant's coinage. Each query should be 12 to 30 words."""

DECOMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "A neutral 4-10 word technical name for the invention.",
        },
        "restatement": {
            "type": "string",
            "description": "One or two sentences restating the invention in "
            "examiner-neutral technical language.",
        },
        "elements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "E1, E2, E3, ..."},
                    "label": {
                        "type": "string",
                        "description": "2-5 word name for this feature.",
                    },
                    "text": {
                        "type": "string",
                        "description": "One sentence stating the feature precisely.",
                    },
                },
                "required": ["id", "label", "text"],
                "additionalProperties": False,
            },
        },
        "queries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Q1, Q2, Q3, ..."},
                    "angle": {
                        "type": "string",
                        "description": "2-5 words naming what this angle targets.",
                    },
                    "text": {"type": "string"},
                },
                "required": ["id", "angle", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "restatement", "elements", "queries"],
    "additionalProperties": False,
}


ASSESS_SYSTEM = """You are a patent examiner assessing candidate prior art \
against a list of claim elements.

For every reference, decide for every element whether the reference teaches it:

- "covered"  — the reference clearly teaches this element.
- "partial"  — the reference teaches something adjacent, or teaches the element \
only in a narrower or different context.
- "absent"   — the reference does not teach this element.

EVIDENCE RULE, and it is absolute: for "covered" and "partial" you must supply \
a `quote` copied CHARACTER-FOR-CHARACTER from that reference's abstract as \
given to you. Do not paraphrase, do not repair grammar, do not join text from \
two places, do not add ellipses. Copy a contiguous span of 5 to 30 words. \
Quotes are checked against the source text automatically and a quote that does \
not match verbatim causes the finding to be downgraded. If no span of the \
abstract supports the level, the level is "absent" and the quote is "".

Judge only what the abstract in front of you actually says. Abstracts are \
short; a reference genuinely not teaching an element is the common case and \
"absent" is the expected answer far more often than "covered". Do not infer \
from the field of the patent that it must teach a feature it never mentions.

`relevance` is 0-100 for how close this reference is to the invention as a \
whole. `note` is one sentence, under 25 words, on what this reference actually \
teaches and where it diverges from the invention. Write it about that \
reference alone — never open with its own id and never mention another \
reference's id, because the references are renumbered before display."""

ASSESS_SCHEMA = {
    "type": "object",
    "properties": {
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ref_id": {"type": "string"},
                    "relevance": {"type": "integer"},
                    "note": {"type": "string"},
                    "coverage": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "element_id": {"type": "string"},
                                "level": {
                                    "type": "string",
                                    "enum": ["covered", "partial", "absent"],
                                },
                                "quote": {"type": "string"},
                            },
                            "required": ["element_id", "level", "quote"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["ref_id", "relevance", "note", "coverage"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["assessments"],
    "additionalProperties": False,
}
