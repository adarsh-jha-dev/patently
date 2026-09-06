# Patently retrieval + analysis service.
#
# Two decisions drive the size and the cold-start time.
#
# CPU-only torch. The default PyPI wheel bundles CUDA kernels for a machine
# that has no GPU, which costs roughly 2 GB. PyTorch publish a CPU index; the
# version is identical so the later `pip install -r` sees it satisfied.
#
# The model is baked into the image. bert-for-patents is 1.3 GB, and a service
# that downloads it on first request pays that on every cold start and fails
# entirely if the Hub is unreachable. Downloading at build time makes start-up
# a local disk read instead.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/huggingface \
    TRANSFORMERS_VERBOSITY=error

WORKDIR /app

RUN pip install --upgrade pip

# Ordered so the expensive layers cache: torch, then the rest, then the model,
# then finally the source that actually changes between deploys.
RUN pip install torch==2.12.0 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-fetch the weights. sentence-transformers wraps a plain BERT checkpoint
# here, so this warns about creating a mean-pooling model — expected, and the
# same thing that happens at runtime.
ARG EMBED_MODEL=anferico/bert-for-patents
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('${EMBED_MODEL}')" \
    && find /opt/huggingface -name '*.h5' -delete \
    && find /opt/huggingface -name 'tf_model*' -delete

COPY main.py ./
COPY patently ./patently

# Hugging Face Spaces routes to 7860; Cloud Run and Fly inject $PORT. Both are
# honoured, with 7860 as the default so a bare `docker run -p 7860:7860` works.
ENV PORT=7860
EXPOSE 7860

# A non-root user, and a writable HF_HOME — some Spaces runtimes mount the
# working directory read-only, and transformers wants to touch its cache.
RUN useradd --create-home --uid 1000 patently \
    && chown -R patently:patently /app /opt/huggingface
USER patently

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
