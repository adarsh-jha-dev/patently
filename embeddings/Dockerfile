# Patently retrieval + analysis service.
#
# Only needed where the deployment takes containers (Cloud Run, Fly, a VM). The
# Hugging Face Space uses the Gradio SDK and `app.py` instead, because Docker
# Spaces require a paid plan.
#
# The model is baked in: bert-for-patents is 1.3 GB, and downloading it on
# first request means paying that on every cold start and failing outright when
# the Hub is unreachable.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/huggingface \
    TRANSFORMERS_VERBOSITY=error

WORKDIR /app

RUN pip install --upgrade pip

# torch first, as its own layer: it is the slowest install and changes least.
# requirements.txt pins the same CPU build, so the later install sees it
# satisfied rather than pulling a second copy.
RUN pip install torch==2.12.0 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

# The user is created, and the cache directory given away, while that directory
# is still EMPTY. Doing this after the download instead makes `chown -R` rewrite
# every weight file into a second layer — measured at a wasted 1.38 GB, since a
# layer records the changed files whether or not their contents differ.
RUN useradd --create-home --uid 1000 patently \
    && mkdir -p "$HF_HOME" \
    && chown -R patently:patently /app "$HF_HOME"

USER patently

# Pre-fetch the weights as the runtime user. sentence-transformers wraps a plain
# BERT checkpoint here, so this warns about creating a mean-pooling model —
# expected, and the same thing that happens at runtime.
ARG EMBED_MODEL=anferico/bert-for-patents
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('${EMBED_MODEL}')" \
    && find "$HF_HOME" -name '*.h5' -delete \
    && find "$HF_HOME" -name 'tf_model*' -delete

# Last, so editing the service does not invalidate the model layer above.
COPY --chown=patently:patently main.py ./
COPY --chown=patently:patently patently ./patently

# Spaces route to 7860; Cloud Run and Fly inject $PORT. Both are honoured.
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
