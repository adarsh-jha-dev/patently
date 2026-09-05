"""
Embedding + vector search, including the multi-angle fusion that makes the
analysis pipeline better than a single similarity query.

The key idea: one embedding of a whole invention description is a bad query.
Averaging a paragraph into a single 1024-dim point washes out exactly the
specific mechanisms that determine novelty. So we embed several targeted
angles instead and fuse the ranked lists.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Iterable, Optional

import torch
from qdrant_client import QdrantClient
from qdrant_client.models import QuantizationSearchParams, SearchParams
from sentence_transformers import SentenceTransformer

from . import config

# The cloud collection is int8-quantized in RAM with float32 originals on disk.
# Over-fetch 2x on the fast vectors and rescore against the exact ones, so the
# ordering matches an unquantized collection. Local mode ignores this.
SEARCH_PARAMS = SearchParams(
    quantization=QuantizationSearchParams(rescore=True, oversampling=2.0)
)


def pick_device() -> str:
    """Apple Silicon GPU when available, else CUDA, else CPU."""
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def stable_point_id(key: str) -> int:
    """
    Deterministic 63-bit point id for a corpus key.

    This replaces `abs(hash(key))`. Python salts string hashing per process
    (PYTHONHASHSEED), so `hash()` returns a *different* id for the same patent
    on every run — which meant a resumed index run re-inserted every document
    under a fresh id instead of updating it, silently duplicating the corpus.
    blake2b is stable across processes, machines, and interpreter versions.
    """
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).hexdigest()
    return int(digest, 16) >> 1  # >> 1 keeps it inside Qdrant's u64/i64 range


class Embedder:
    def __init__(self, device: Optional[str] = None, half: bool = False):
        """
        `half` runs the model in fp16 — 2.75x faster on MPS, with cosine
        similarity >= 0.9995 against the fp32 embedding of the same text and
        unchanged top-10 neighbours. Worth it for an index build, not for the
        4-6 query vectors an analysis embeds.
        """
        self.device = device or pick_device()
        self.model = SentenceTransformer(config.EMBED_MODEL, device=self.device)
        if half:
            self.model = self.model.half()
        self.half = half
        dim = self.model.get_sentence_embedding_dimension()
        if dim != config.VECTOR_SIZE:
            # Fail loudly at startup rather than writing wrong-width vectors
            # into a live collection.
            raise RuntimeError(
                f"{config.EMBED_MODEL} produced {dim}-dim vectors but "
                f"config.VECTOR_SIZE is {config.VECTOR_SIZE}. Fix the constant "
                "and recreate the collection."
            )
        self.dim = dim

    def encode(self, texts: Iterable[str], batch_size: int = 32) -> list[list[float]]:
        texts = [t[: config.MAX_EMBED_CHARS] for t in texts]
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
            # Normalising makes cosine == dot product, so score arithmetic
            # downstream (fusion, thresholds) stays interpretable.
            normalize_embeddings=True,
        )
        return vectors.tolist()


class Store:
    def __init__(self, client: QdrantClient):
        self.client = client

    @classmethod
    def from_env(cls) -> Optional["Store"]:
        # Local embedded mode wins when set: it is the offline path, and if
        # someone has deliberately pointed at a local directory we should not
        # silently prefer a stale cloud URL still sitting in .env.
        if config.QDRANT_PATH:
            return cls(QdrantClient(path=config.QDRANT_PATH))
        if not config.QDRANT_URL:
            return None
        return cls(
            QdrantClient(
                url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY, timeout=30
            )
        )

    @property
    def mode(self) -> str:
        return "local" if config.QDRANT_PATH else "cloud"

    def close(self) -> None:
        """
        Release the client (and, in local mode, the directory lock).

        Without this the local backend is closed from __del__ during
        interpreter shutdown, which raises `ImportError: sys.meta_path is
        None` and buries whatever real error preceded it.
        """
        try:
            self.client.close()
        except Exception:
            pass

    def count(self) -> int:
        return self.client.get_collection(config.COLLECTION).points_count or 0

    def search(self, vector: list[float], limit: int) -> list[dict[str, Any]]:
        points = self.client.query_points(
            collection_name=config.COLLECTION,
            query=vector,
            limit=limit,
            with_payload=True,
            search_params=SEARCH_PARAMS,
        ).points
        return [
            {
                "patent_id": str(p.payload.get("patent_id", p.id)),
                "title": p.payload.get("title") or "",
                "abstract": p.payload.get("abstract") or "",
                "score": float(p.score),
            }
            for p in points
        ]

    async def search_many(
        self, vectors: list[list[float]], limit: int
    ) -> list[list[dict[str, Any]]]:
        """Run several queries concurrently. qdrant-client is sync, so each
        search goes to a worker thread — network-bound, so this is a real win."""
        return await asyncio.gather(
            *(asyncio.to_thread(self.search, v, limit) for v in vectors)
        )


def fuse(
    result_sets: list[list[dict[str, Any]]],
    query_ids: list[str],
    k: int = 60,
) -> list[dict[str, Any]]:
    """
    Reciprocal Rank Fusion over per-angle result lists.

    RRF scores a document by sum(1 / (k + rank)) across the lists it appears
    in, so a patent that shows up mid-pack for *three* different angles
    outranks one that tops a single angle. That is precisely the prior-art
    signal we want: broad relevance to the invention rather than a lexical
    coincidence with one phrasing. Rank-based fusion also sidesteps the fact
    that cosine scores from different queries aren't on a comparable scale.
    """
    merged: dict[str, dict[str, Any]] = {}
    for qid, results in zip(query_ids, result_sets):
        for rank, hit in enumerate(results):
            pid = hit["patent_id"]
            entry = merged.get(pid)
            if entry is None:
                entry = {**hit, "found_by": [], "rrf": 0.0, "best_score": hit["score"]}
                merged[pid] = entry
            entry["rrf"] += 1.0 / (k + rank + 1)
            entry["best_score"] = max(entry["best_score"], hit["score"])
            if qid not in entry["found_by"]:
                entry["found_by"].append(qid)

    ordered = sorted(merged.values(), key=lambda e: e["rrf"], reverse=True)
    return ordered
