"""
Patently — retrieval + analysis service.

Routes:
  GET  /health   liveness, plus which model/provider/corpus is actually wired up
  POST /embed    text -> 1024-dim vectors
  POST /search   plain semantic search over the patent index
  POST /analyze  the full prior-art analysis (buffered JSON)
  POST /analyze/stream
                 the same analysis as Server-Sent Events, so the UI can show
                 progress across a pipeline that takes 10-30s

Run locally:
  cd embeddings && uvicorn main:app --reload --port 8000

The embedding model auto-detects MPS on Apple Silicon, then CUDA, then CPU.
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from patently import config
from patently.analyze import run_analysis
from patently.llm import provider_status
from patently.retrieval import Embedder, Store
from patently.schemas import (
    AnalyzeRequest,
    AnalyzeResult,
    EmbedRequest,
    EmbedResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading bert-for-patents takes 5-10s, so it happens once here rather
    # than per request. Everything shared lives on app.state so it is scoped
    # to the app lifecycle instead of module import.
    print(f"[startup] loading {config.EMBED_MODEL}...")
    app.state.embedder = Embedder()
    print(f"[startup] model ready on {app.state.embedder.device} "
          f"(dim={app.state.embedder.dim})")

    app.state.store = Store.from_env()
    if app.state.store is None:
        print("[startup] no QDRANT_URL / QDRANT_PATH — /search and /analyze "
              "are disabled")
    else:
        try:
            print(f"[startup] qdrant ({app.state.store.mode}): "
                  f"{app.state.store.count():,} points in '{config.COLLECTION}'")
        except Exception as e:
            print(f"[startup] qdrant reachable but collection check failed: {e}")

    status = provider_status()
    if not status["key_present"]:
        print(f"[startup] warning: no API key for provider '{status['provider']}' "
              "— /analyze will fail")
    else:
        print(f"[startup] reasoning: {status['provider']}/{status['model']}")

    yield

    if app.state.store is not None:
        app.state.store.close()  # releases the local directory lock
    print("[shutdown] bye")


app = FastAPI(title="Patently", lifespan=lifespan)

# The Next.js app calls this service directly in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_store(app: FastAPI) -> Store:
    if app.state.store is None:
        raise HTTPException(
            503, "qdrant not configured (set QDRANT_URL or QDRANT_PATH)"
        )
    return app.state.store


@app.get("/health")
def health():
    points = None
    if app.state.store is not None:
        try:
            points = app.state.store.count()
        except Exception:
            points = -1  # reachable config, unreachable collection
    return {
        "ok": True,
        "embed_model": config.EMBED_MODEL,
        "device": app.state.embedder.device,
        "dim": app.state.embedder.dim,
        "collection": config.COLLECTION,
        "store_mode": app.state.store.mode if app.state.store else None,
        "indexed_points": points,
        "reasoning": provider_status(),
    }


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest):
    vectors = app.state.embedder.encode(req.texts)
    return EmbedResponse(
        embeddings=vectors,
        dim=app.state.embedder.dim,
        device=app.state.embedder.device,
    )


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    """Plain single-query semantic search. The interesting endpoint is /analyze;
    this one is here for debugging the index and for callers that just want
    nearest neighbours."""
    store = _require_store(app)
    vector = app.state.embedder.encode([req.query])[0]
    try:
        results = store.search(vector, req.limit)
    except Exception as e:
        raise HTTPException(503, f"qdrant query failed: {e}")
    return SearchResponse(hits=[SearchHit(**r) for r in results])


@app.post("/analyze", response_model=AnalyzeResult)
async def analyze(req: AnalyzeRequest):
    store = _require_store(app)
    try:
        return await run_analysis(
            req.description, app.state.embedder, store, top_k=req.top_k
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(502, f"analysis failed: {e}")


@app.post("/analyze/stream")
async def analyze_stream(req: AnalyzeRequest):
    """
    Same pipeline, streamed as SSE.

    The pipeline takes 10-30s end to end and the intermediate stages (the
    claim decomposition, the search angles) are genuinely worth showing — they
    are how the user tells whether the system understood the invention before
    the results land.
    """
    store = _require_store(app)

    async def gen():
        # A real queue plus a background task: the naive version (buffer the
        # events and drain after awaiting the pipeline) delivers every
        # progress event at once when the work is already done, which is the
        # opposite of streaming.
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def push(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        async def on_progress(stage: str, payload: dict):
            await queue.put(push(stage, payload))

        started = time.time()

        async def run():
            try:
                result = await run_analysis(
                    req.description,
                    app.state.embedder,
                    store,
                    top_k=req.top_k,
                    on_progress=on_progress,
                )
                payload = result.model_dump()
                payload["elapsed_ms"] = int((time.time() - started) * 1000)
                await queue.put(push("result", payload))
            except Exception as e:
                await queue.put(push("error", {"message": str(e)}))
            finally:
                await queue.put(None)  # sentinel: closes the stream

        task = asyncio.create_task(run())
        yield push("start", {"message": "Starting analysis"})
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            # Client hung up mid-analysis — don't leave the pipeline running.
            if not task.done():
                task.cancel()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
