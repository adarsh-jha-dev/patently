"""
Single source of truth for configuration.

Everything that both the service and the offline scripts need to agree on
lives here — collection name, vector size, model id. Historically these were
duplicated across main.py and scripts/, and they drifted (main.py's docstring
claimed 768 dims while init_collection.py created a 1024-dim collection).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# ---- retrieval -------------------------------------------------------------

EMBED_MODEL = os.getenv("PATENTLY_EMBED_MODEL", "anferico/bert-for-patents")

# bert-for-patents is a BERT-Large architecture: hidden size 1024, not 768.
# This is asserted against the loaded model at startup so the two can't drift.
VECTOR_SIZE = 1024

COLLECTION = os.getenv("PATENTLY_COLLECTION", "patents")

# Recorded on every saved analysis. Change it whenever the indexed corpus
# changes, so old rows keep saying what they were actually searched against.
CORPUS = os.getenv("PATENTLY_CORPUS", "big_patent:g")

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# Local embedded mode. qdrant-client can run the engine in-process against a
# directory on disk — no server, no cloud cluster, no Docker. Set QDRANT_PATH
# and it takes precedence over QDRANT_URL, which makes the whole stack
# runnable offline. The directory is locked exclusively while open, so the
# indexer and the service cannot both hold it at once.
_qdrant_path = os.getenv("QDRANT_PATH")
# Resolved against the project root, never the CWD. The scripts run from the
# repo root and the service runs from embeddings/, so a bare relative path
# would silently point the two at different directories — the service comes up
# healthy against an empty collection and nothing says why.
QDRANT_PATH = (
    str((ROOT / _qdrant_path).resolve()) if _qdrant_path else None
)

# bert-for-patents truncates at 512 wordpieces. Abstracts almost always fit;
# this cap keeps the odd runaway abstract from silently eating the window.
MAX_EMBED_CHARS = 2000

# ---- reasoning layer -------------------------------------------------------
#
# Provider-neutral. Both providers are called over plain HTTP (httpx) rather
# than through their SDKs — the two request shapes we need (JSON-schema
# constrained output) are small enough that a vendored adapter is less code
# than two SDK dependencies, and it keeps swapping providers to one env var.

LLM_PROVIDER = os.getenv("PATENTLY_LLM_PROVIDER", "gemini").lower()

# Deliberately cheap defaults for the dev phase. Both are plain env vars, so
# moving to a stronger model in production is a one-line change with no code
# edits — see README "Choosing a model".
GEMINI_MODEL = os.getenv("PATENTLY_GEMINI_MODEL", "gemini-3.5-flash-lite")
OPENAI_MODEL = os.getenv("PATENTLY_OPENAI_MODEL", "gpt-5.4-mini")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ---- analysis tuning -------------------------------------------------------

# How many candidates survive retrieval and get sent to the assessment call.
# This is the single biggest cost knob: the assess prompt is ~O(K * 1200 chars).
ASSESS_TOP_K = int(os.getenv("PATENTLY_ASSESS_TOP_K", "12"))

# Per-query retrieval depth before fusion. Wider than ASSESS_TOP_K on purpose —
# fusion needs overlap between angles to be able to reward it.
RETRIEVE_PER_QUERY = int(os.getenv("PATENTLY_RETRIEVE_PER_QUERY", "25"))

# Abstract characters handed to the LLM per candidate. Full abstracts average
# ~1100 chars in BIGPATENT, so this truncates only the long tail.
ASSESS_ABSTRACT_CHARS = 1400
