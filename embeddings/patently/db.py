"""
Saved analyses.

One table. `result` is JSONB because the AnalyzeResult shape is still moving and
a migration per field would make changing the pipeline expensive; the few scalar
columns exist only so the listing query need not deserialise every row.

Every row records the corpus it ran against — "Inconclusive" over 8,220
abstracts and over 258,935 are different claims, and without `corpus_size` you
cannot tell them apart later.

Optional throughout: with DATABASE_URL unset, `connect` returns None and every
call site degrades to not saving.
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
    Managed providers hand out libpq-style `?sslmode=require`, which asyncpg
    does not parse — it takes an `ssl=` argument and raises on the unknown
    parameter, surfacing as what looks like a credentials error. Translate it.
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
    A slug is the only thing between an unlisted analysis and anyone who can
    type a URL, so this is a CSPRNG rather than a counter.
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
