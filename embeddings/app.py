"""
Hugging Face Space entrypoint.

Spaces runs this file. Docker Spaces require a paid plan, but the Gradio SDK is
free on CPU Basic (2 vCPU, 16 GB) — more than enough for BERT-Large — so the
service is mounted inside a Gradio app rather than shipped as a container. The
FastAPI routes are the product; the Gradio page exists so the Space URL shows
something useful instead of a 404.

Caches are redirected to /tmp before transformers is imported: a Space's
working directory is read-only, and the default cache location fails there.

`Dockerfile` is still the right entrypoint anywhere that supports containers
(Cloud Run, Fly, a VM). This file changes nothing about the service itself.
"""

import os
from pathlib import Path

# Must precede any transformers/sentence-transformers import.
_CACHE = Path(os.getenv("HF_HOME", "/tmp/huggingface"))
_CACHE.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(_CACHE)
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

import gradio as gr  # noqa: E402

from main import app as service  # noqa: E402  (starts the model on lifespan)
from patently import config  # noqa: E402


def search(query: str, limit: int = 5) -> str:
    """Nearest-neighbour lookup, so the Space page is self-demonstrating."""
    query = (query or "").strip()
    if not query:
        return "Enter a description to search for."

    store = getattr(service.state, "store", None)
    embedder = getattr(service.state, "embedder", None)
    if store is None or embedder is None:
        return "The service is still starting — try again in a moment."

    try:
        hits = store.search(embedder.encode([query])[0], limit)
    except Exception as exc:  # a broken index should not blank the page
        return f"Search failed: {type(exc).__name__}: {exc}"
    if not hits:
        return "Nothing found in the indexed corpus."

    return "\n\n".join(
        f"**{h['patent_id']}** · score {h['score']:.3f}\n\n{h['abstract'][:400]}…"
        for h in hits
    )


with gr.Blocks(title="Patently Service", analytics_enabled=False) as demo:
    gr.Markdown(
        f"""
        # Patently — retrieval + analysis service

        The API behind [Patently](https://github.com/adarsh-jha-dev/patently):
        prior art analysis over an indexed patent corpus. The web front end
        calls this; it is not meant to be used directly.

        Corpus: **BIGPATENT subset G** (physics and computing), grants through
        roughly 2014. Embeddings from `{config.EMBED_MODEL}`.

        Interactive API docs: [`/docs`](/docs) · health: [`/health`](/health)

        Below is plain nearest-neighbour search — the raw retrieval step,
        without the claim decomposition or coverage analysis that the full
        pipeline adds.
        """
    )
    box = gr.Textbox(
        label="Describe an invention",
        placeholder="a touchscreen controller that rejects display noise across multiple drive frequencies",
        lines=3,
    )
    count = gr.Slider(1, 10, value=5, step=1, label="Results")
    out = gr.Markdown()
    gr.Button("Search", variant="primary").click(search, [box, count], out)


# The FastAPI app is the parent, so /health, /analyze and the rest stay at the
# root and the Gradio page is mounted alongside them.
app = gr.mount_gradio_app(service, demo, path="/ui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
