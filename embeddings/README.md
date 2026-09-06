---
title: Patently Service
emoji: 🔍
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Patently — retrieval + analysis service

The Python half of [Patently](https://github.com/adarsh-jha-dev/patently): prior
art analysis over an indexed patent corpus. The web front end talks to this;
the browser never does.

This directory doubles as a Hugging Face Space. The frontmatter above is what
HF reads — `sdk: docker` builds the `Dockerfile` here, and `app_port: 7860`
matches the port it listens on.

## Routes

| Route | Purpose |
|---|---|
| `GET /health` | model, device, store mode, indexed point count, provider, live limits |
| `POST /embed` | texts → 1024-dim vectors |
| `POST /search` | plain nearest-neighbour search |
| `POST /analyze` | full analysis, buffered JSON |
| `POST /analyze/stream` | same pipeline as SSE, with progress events |
| `GET /analyses` | recent saved analyses (needs `DATABASE_URL`) |
| `GET /analyses/{slug}` | one saved analysis |

## Configuration

Required:

| Variable | Notes |
|---|---|
| `GEMINI_API_KEY` | or `OPENAI_API_KEY` with `PATENTLY_LLM_PROVIDER=openai` |
| `QDRANT_URL` | the cluster holding the indexed corpus |
| `QDRANT_API_KEY` | |

Optional:

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | unset | saves analyses and enables permalinks; unset means no saving |
| `PATENTLY_RATE_LIMIT` | `5` | analyses per client per window |
| `PATENTLY_RATE_WINDOW` | `3600` | window in seconds |
| `PATENTLY_DAILY_BUDGET` | `200` | analyses per UTC day, all clients |
| `PATENTLY_CORPUS` | `big_patent:g` | recorded on saved analyses |
| `PATENTLY_CORS_ORIGINS` | — | extra origins, comma-separated |

**Do not set `QDRANT_PATH` in a deployment.** It takes precedence over
`QDRANT_URL` and points the service at a local embedded store that will not
exist in the container.

## Running locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Or via the image, which is what gets deployed:

```bash
docker build -t patently-service .
docker run -p 7860:7860 --env-file ../.env patently-service
```

## Limits

`/analyze` costs two LLM calls against one shared key, so the public deployment
caps analyses per client and per day. Both return `429` with `Retry-After` and
a message saying which limit was hit. `GET /health` reports the current budget.
