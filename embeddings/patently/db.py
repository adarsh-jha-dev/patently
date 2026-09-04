"""
Saved analyses.

One table. An analysis is expensive to produce (two LLM calls and a retrieval
pass, 10-30s) and currently evaporates the moment the tab closes — so it gets a
row and a shareable slug.

TWO DESIGN CHOICES WORTH THE WORDS
----------------------------------
1. `result` is JSONB, not columns. The AnalyzeResult shape is still moving
   (`rubric_fields` landed in stats this week), and a schema migration per
   field would make changing the pipeline expensive in exactly the phase where
   it should be cheap. The handful of scalars that get their own columns —
   title, score, label — exist only so the listing query does not have to
   deserialise every row, and `result` stays the source of truth for all of
   them.

2. Every row records the corpus it ran against. A saved verdict is meaningless
   without knowing how much index existed when it was produced: "Inconclusive"
   against 8,220 abstracts and "Inconclusive" against 258,935 are completely
   different claims, and without `corpus_size` you cannot tell them apart a
   month later. It is also what makes a future corpus change legible instead of
   mysterious — old rows keep saying what they actually searched.

The whole module is optional. With DATABASE_URL unset, `Database.connect`
returns None and every call site degrades to not saving. Persistence is a
feature of the service, never a requirement for running it.
"""

from __future__ import annotations

import json
import os
import secrets
import ssl
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:  # asyncpg is optional — the service runs without it
    import asyncpg
except ImportError:  # pragma: no cover - exercised by absence, not by tests
    asyncpg = None  # type: ignore[assignment]

DATABASE_URL = os.getenv("DATABASE_URL") or ""

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id            uuid        PRIMARY KEY,
    slug          text        UNIQUE NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),

    description   text        NOT NULL,
    rubric        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    result        jsonb       NOT NULL,

    -- Denormalised for the listing query only. `result` remains authoritative.
    title         text        NOT NULL,
    label         text        NOT NULL,
    novelty_score integer,
    conclusive    boolean     NOT NULL,

    -- What this verdict was actually produced against.
    corpus        text        NOT NULL,
    corpus_size   integer     NOT NULL,
    model         text        NOT NULL,
    elapsed_ms    integer
);

CREATE INDEX IF NOT EXISTS analyses_created_at_idx
    ON analyses (created_at DESC);
"""


def normalise_dsn(url: str) -> tuple[str, Optional[ssl.SSLContext]]:
    """
    Turn a hosted-Postgres URL into something asyncpg accepts.

    Neon, Supabase and friends hand out `...?sslmode=require`, which is libpq
    syntax. asyncpg does not parse it — it takes an `ssl=` argument instead and
    raises on the unknown parameter, which surfaces as a connection error that
    looks like a credentials problem and is not. Strip the libpq-only query
    parameters and translate them.

    `postgresql+asyncpg://` (SQLAlchemy's dialect form) is also accepted and
    reduced, since that is what most copy-pasted examples use.
    """
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    params = dict(parse_qsl(parsed.query))

    sslmode = params.pop("sslmode", None)
    params.pop("channel_binding", None)  # libpq-only, asyncpg rejects it

    context: Optional[ssl.SSLContext] = None
    if sslmode in ("require", "prefer", "allow"):
        # These modes encrypt without verifying the certificate chain, which is
        # what the managed providers' default connection strings mean.
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif sslmode in ("verify-ca", "verify-full"):
        context = ssl.create_default_context()

    cleaned = parsed._replace(query=urlencode(params))
    return urlunparse(cleaned), context


def new_slug() -> str:
    """
    Short, URL-safe, unguessable share token.

    Unguessable matters more than short here: a slug is the only thing standing
    between an unlisted analysis and anyone who can type a URL, so this is a
    CSPRNG rather than a counter or a hash of the description.
    """
    return secrets.token_urlsafe(9)


def row_summary(row: Any) -> dict[str, Any]:
    """Listing shape — the columns, never the full result blob."""
    return {
        "slug": row["slug"],
        "created_at": row["created_at"].isoformat(),
        "title": row["title"],
        "label": row["label"],
        "novelty_score": row["novelty_score"],
        "conclusive": row["conclusive"],
        "corpus": row["corpus"],
        "corpus_size": row["corpus_size"],
    }


class Database:
    def __init__(self, pool: "asyncpg.Pool"):
        self.pool = pool

    @classmethod
    async def connect(cls) -> Optional["Database"]:
        """Returns None whenever persistence is not configured or unavailable."""
        if not DATABASE_URL.strip():
            return None
        if asyncpg is None:
            print("[db] DATABASE_URL is set but asyncpg is not installed — "
                  "run: pip install asyncpg")
            return None

        dsn, context = normalise_dsn(DATABASE_URL)
        try:
            pool = await asyncpg.create_pool(
                dsn, ssl=context, min_size=1, max_size=4, command_timeout=15
            )
        except Exception as exc:
            # A database that is down must not take the analysis service with
            # it. Saving is a convenience; searching is the product.
            print(f"[db] could not connect ({type(exc).__name__}: {exc}) — "
                  "analyses will not be saved")
            return None

        async with pool.acquire() as conn:
            await conn.execute(SCHEMA)
        return cls(pool)

    async def close(self) -> None:
        await self.pool.close()

    async def save(
        self,
        *,
        description: str,
        rubric: dict[str, Any] | None,
        result: dict[str, Any],
        corpus: str,
        corpus_size: int,
        model: str,
    ) -> Optional[str]:
        """Persist one analysis, returning its slug. None if the write failed."""
        import uuid

        verdict = result.get("verdict") or {}
        slug = new_slug()
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO analyses (
                        id, slug, description, rubric, result, title, label,
                        novelty_score, conclusive, corpus, corpus_size, model,
                        elapsed_ms
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                    """,
                    uuid.uuid4(),
                    slug,
                    description,
                    json.dumps(rubric or {}),
                    json.dumps(result),
                    result.get("title") or "Untitled invention",
                    verdict.get("label") or "Unknown",
                    verdict.get("novelty_score"),
                    bool(verdict.get("conclusive", False)),
                    corpus,
                    corpus_size,
                    model,
                    result.get("elapsed_ms"),
                )
            return slug
        except Exception as exc:
            # Never fail a completed analysis because it could not be filed.
            print(f"[db] save failed ({type(exc).__name__}: {exc})")
            return None

    async def get(self, slug: str) -> Optional[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM analyses WHERE slug = $1", slug
            )
        if row is None:
            return None
        return {
            **row_summary(row),
            "description": row["description"],
            "rubric": json.loads(row["rubric"]),
            "result": json.loads(row["result"]),
            "model": row["model"],
        }

    async def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT slug, created_at, title, label, novelty_score,
                       conclusive, corpus, corpus_size
                FROM analyses ORDER BY created_at DESC LIMIT $1
                """,
                limit,
            )
        return [row_summary(r) for r in rows]
