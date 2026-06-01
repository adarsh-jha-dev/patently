"""
Patently — embeddings service.

A small FastAPI service that:
  1. Loads `bert-for-patents` once at startup (kept in memory).
  2. Exposes /embed for turning text into 768-dim vectors.
  3. Exposes /search for querying the Qdrant patent index.
  4. Exposes /health for liveness checks.

Run locally:
  uvicorn main:app --reload --port 8000

The model auto-detects MPS on Apple Silicon and uses it. CPU fallback otherwise.
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

import torch
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

load_dotenv("../.env")

# ---- config ----------------------------------------------------------------

MODEL_NAME = "anferico/bert-for-patents"
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "patents"


def pick_device() -> str:
    """Use Apple Silicon GPU when available, else CPU. CUDA path here for portability."""
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


# ---- app state -------------------------------------------------------------
#
# Hold the model + qdrant client on app.state so they're shared across
# requests but scoped to the app lifecycle. The lifespan handler below
# loads them once at startup — loading bert-for-patents takes ~5-10s,
# so we definitely don't want that on every request.


@asynccontextmanager
async def lifespan(app: FastAPI):
    device = pick_device()
    print(f"[startup] loading {MODEL_NAME} on {device}...")
    app.state.model = SentenceTransformer(MODEL_NAME, device=device)
    app.state.device = device
    print(f"[startup] model loaded. embedding dim: {app.state.model.get_sentence_embedding_dimension()}")

    if QDRANT_URL:
        app.state.qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        print(f"[startup] qdrant client ready: {QDRANT_URL}")
    else:
        app.state.qdrant = None
        print("[startup] no QDRANT_URL set — /search will be disabled")

    yield  # app runs here

    # cleanup on shutdown (nothing to clean up yet, but the hook is here)
    print("[shutdown] bye")


app = FastAPI(title="Patently embeddings", lifespan=lifespan)


# ---- schemas ---------------------------------------------------------------


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=128)


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    dim: int
    device: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(10, ge=1, le=100)


class SearchHit(BaseModel):
    patent_id: str
    title: Optional[str] = None
    abstract: Optional[str] = None
    score: float


class SearchResponse(BaseModel):
    hits: list[SearchHit]


# ---- routes ----------------------------------------------------------------


@app.get("/health")
def health():
    return {
        "ok": True,
        "model": MODEL_NAME,
        "device": app.state.device,
        "qdrant_connected": app.state.qdrant is not None,
    }


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest):
    """
    Turn a batch of texts into 768-dim vectors.
    Batches up to 128 at a time — bigger batches are faster per-text but
    blow up memory. Tune this when you actually index.
    """
    vectors = app.state.model.encode(
        req.texts,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True,  # makes cosine similarity == dot product, simpler downstream
    )
    return EmbedResponse(
        embeddings=vectors.tolist(),
        dim=vectors.shape[1],
        device=app.state.device,
    )


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    """
    Embed the query, hit Qdrant, return top matches.
    Requires QDRANT_URL to be configured and the collection to exist.
    """
    if app.state.qdrant is None:
        raise HTTPException(503, "qdrant not configured")

    query_vec = app.state.model.encode(
        [req.query],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )[0]

    try:
        results = app.state.qdrant.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vec.tolist(),
            limit=req.limit,
            with_payload=True,
        ).points
    except Exception as e:
        raise HTTPException(503, f"qdrant query failed: {e}")

    hits = [
        SearchHit(
            patent_id=str(r.payload.get("patent_id", r.id)),
            title=r.payload.get("title"),
            abstract=r.payload.get("abstract"),
            score=r.score,
        )
        for r in results
    ]
    return SearchResponse(hits=hits)