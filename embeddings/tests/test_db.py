"""
Tests for the persistence layer that don't need a database.

The DSN normaliser is the piece worth pinning: managed providers hand out
`?sslmode=require`, asyncpg rejects it, and the failure reads like bad
credentials rather than a malformed DSN.

    cd embeddings && python -m pytest tests/ -q
"""

import ssl
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patently.db import SCHEMA, new_slug, normalise_dsn


def test_sslmode_require_is_translated_not_forwarded():
    """Neon and Supabase both hand out exactly this shape."""
    dsn, context = normalise_dsn(
        "postgresql://user:pw@ep-x.eu-central-1.aws.neon.tech/patently?sslmode=require"
    )
    assert "sslmode" not in dsn
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_NONE


def test_channel_binding_is_stripped():
    """Neon appends this too, and asyncpg rejects it the same way."""
    dsn, _ = normalise_dsn(
        "postgresql://u:p@host/db?sslmode=require&channel_binding=require"
    )
    assert "channel_binding" not in dsn
    assert "sslmode" not in dsn


def test_sqlalchemy_dialect_prefix_is_reduced():
    dsn, _ = normalise_dsn("postgresql+asyncpg://u:p@host/db")
    assert dsn.startswith("postgresql://")
    assert "+asyncpg" not in dsn


def test_verify_full_keeps_certificate_checking():
    _, context = normalise_dsn("postgresql://u:p@host/db?sslmode=verify-full")
    assert context is not None
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_plain_dsn_is_left_alone():
    dsn, context = normalise_dsn("postgresql://u:p@localhost:5432/patently")
    assert dsn == "postgresql://u:p@localhost:5432/patently"
    assert context is None


def test_unrelated_query_parameters_survive():
    """Only the libpq-only parameters should be removed."""
    dsn, _ = normalise_dsn(
        "postgresql://u:p@host/db?sslmode=require&application_name=patently"
    )
    assert "application_name=patently" in dsn


def test_credentials_survive_normalisation():
    dsn, _ = normalise_dsn("postgresql://user:p%40ss@host:5432/db?sslmode=require")
    assert "user:p%40ss@host:5432" in dsn


def test_slugs_are_unique_and_url_safe():
    slugs = {new_slug() for _ in range(2000)}
    assert len(slugs) == 2000
    for s in slugs:
        assert s == s.strip()
        # No percent-encoding needed to put one of these in a path segment.
        assert all(c.isalnum() or c in "-_" for c in s), s


def test_slug_has_enough_entropy_to_be_unguessable():
    """A slug is the only thing protecting an unlisted analysis."""
    assert len(new_slug()) >= 12


@pytest.mark.parametrize(
    "column",
    ["corpus", "corpus_size", "slug", "result", "rubric", "conclusive"],
)
def test_schema_records_what_a_verdict_was_produced_against(column):
    """`Inconclusive` against 8k and against 258k are different claims; a row
    that cannot tell them apart is not worth keeping."""
    assert column in SCHEMA


def test_schema_is_idempotent():
    """Startup runs this on every boot."""
    assert SCHEMA.count("IF NOT EXISTS") >= 2
