# Patently

> Prior art analysis for inventions. Describe what you're building in plain
> English; get back which *parts* of it the prior art already teaches — element
> by element, with the passage behind every finding.

## Why this isn't a search box

A semantic search over patents returns ten documents that look like your
invention. That is the easy half, and it is roughly what a good Google Patents
query already does. It doesn't answer the question you actually have, which is
**which parts of my invention are already taught, and by what.**

Patently answers that one instead:

- **Claim-element decomposition.** Your description is broken into the discrete
  technical features a novelty search has to clear — the way an independent
  claim's limitations decompose.
- **Multi-angle retrieval.** One embedding of a whole paragraph averages away
  the specifics that determine novelty. Patently searches 4–6 targeted angles
  separately and fuses the rankings with Reciprocal Rank Fusion, so a patent
  that ranks mid-pack for *three* angles beats one that tops a single angle.
- **A coverage map.** Every claim element × every reference, each filled cell
  backed by a quote **verified verbatim against the source abstract**. A
  citation that can't be located in the source is downgraded automatically, so
  a fabricated quote can never drive a finding.
- **Novelty whitespace.** The elements *nothing* found teaches. This is the
  output a search engine structurally cannot give you: an absence only means
  something if you know what was searched and what came back.
- **Combination risk.** Pairs of references that *together* read on more than
  either does alone — the shape of a §103 obviousness rejection. Found by
  exhaustive set arithmetic over the coverage matrix, not by asking a model, so
  the same inputs always give the same pairs.

And when the corpus has nothing in your field, it says **Inconclusive** rather
than reporting a clean 100/100. A tool that mistakes an empty index for a
novelty clearance is worse than no tool.

## How it works

```
description ──► decompose         (1 LLM call)  elements + search angles
            ──► retrieve          (0 LLM calls) batch embed, parallel search, RRF fuse
            ──► assess            (1 LLM call)  element × reference coverage + quotes
            ──► synthesise        (0 LLM calls) grounding check, whitespace, §103 pairs
```

**Two LLM calls per analysis**, regardless of how many candidates come back.
Everything computable is computed rather than asked — which is also why the
combination analysis and the scoring are reproducible.

## Stack

- **web/** — Next.js 15, TypeScript, Tailwind v4. Streams the pipeline over SSE.
- **embeddings/** — FastAPI + `patently/` package. Owns the model and the pipeline.
- **Qdrant** for vectors — cloud, or embedded locally with no server at all.
- **Gemini or OpenAI** for the reasoning layer, behind one provider-neutral adapter.

## Setup

```bash
cp .env.example .env      # fill in GEMINI_API_KEY (or OPENAI_API_KEY)

cd embeddings
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 1. Build an index

The default `.env` uses **local embedded Qdrant** (`QDRANT_PATH=./.qdrant`) —
no server, no cloud account, no Docker. To use a cloud cluster instead, set
`QDRANT_URL` + `QDRANT_API_KEY` and leave `QDRANT_PATH` unset.

```bash
python scripts/init_collection.py
python scripts/build_index.py --limit 2000   # smoke test
python scripts/build_index.py                # full run, resumes if interrupted
```

Indexing runs ~13 patents/sec on Apple Silicon (MPS), so the full ~290k
BIGPATENT "g" subset is about 6 hours. It checkpoints by stream position and
resumes cleanly.

> Local embedded mode takes an exclusive lock on the directory — the indexer
> and the service can't hold it at the same time.

### 2. Run it

```bash
# service
cd embeddings && uvicorn main:app --reload --port 8000

# web app
cd web && npm install && npm run dev     # http://localhost:3000
```

Or skip the browser entirely:

```bash
python scripts/analyze.py "an invention description..."
python scripts/analyze.py --file disclosure.txt --json > report.json
```

## Choosing a provider

Both providers go through one adapter over plain HTTP, so switching is an env
var and no code change:

```bash
PATENTLY_LLM_PROVIDER=gemini    # or: openai
PATENTLY_GEMINI_MODEL=gemini-3.5-flash-lite
PATENTLY_OPENAI_MODEL=gpt-5.4-mini
```

Verify a provider before running a real analysis — this checks the key, the
model id, and makes one live schema-constrained call:

```bash
python scripts/check_provider.py --all
```

Model ids go stale faster than any table in a README, so `check_provider.py`
lists what your key can actually see and names the closest matches when a
configured id is gone. Use it to pick a current cheap model rather than
trusting the defaults above.

The defaults are deliberately cheap for development. Because the pipeline is
fixed at two calls, moving up a tier changes cost linearly and predictably.

### Provider differences the adapter handles

The two APIs disagree in ways that would otherwise be your problem:

- **Schema dialect.** Schemas are authored in OpenAI's strict dialect
  (`additionalProperties: false`, every property required — both mandatory
  there) and down-converted for Gemini, which rejects those keywords.
- **Parameter drift.** OpenAI's reasoning models reject `temperature` and
  `max_tokens`, while older models reject `max_completion_tokens`, and the
  model id doesn't reliably tell you which family you're in. Rather than
  keeping a model table that goes stale, the adapter sends the modern
  parameters and lets a 400 correct it once per process.
- **Refusals and truncation.** Both come back as HTTP 200 with unusable
  content; they're detected explicitly instead of surfacing as a JSON parse
  error 30 seconds into an analysis.

## API

| Route | Purpose |
|---|---|
| `GET /health` | model, device, store mode, indexed point count, provider |
| `POST /embed` | texts → 1024-dim vectors |
| `POST /search` | plain nearest-neighbour search (index debugging) |
| `POST /analyze` | full analysis, buffered JSON |
| `POST /analyze/stream` | same pipeline as SSE, with progress events |

## Tests

```bash
cd embeddings && python -m pytest tests/ -q
```

36 tests, no network and no API key required. They cover the parts that decide
what a user is told — quote grounding, rank fusion, the §103 arithmetic, the
inconclusive guard — plus the OpenAI transport, which is exercised against a
local stand-in server so the path stays tested without a key.

## Status

Working end to end: pipeline, both providers, local + cloud vector store, CLI,
and web UI.

- [x] Embeddings service
- [x] Corpus indexing (resumable, position-checkpointed)
- [x] Decomposition + multi-angle retrieval + assessment agent
- [x] Coverage map, whitespace, §103 combination analysis
- [x] Web UI
- [x] Multi-provider LLM support (Gemini / OpenAI)
- [ ] Full 290k corpus indexed (currently partial)
- [ ] Postgres metadata layer — real patent numbers, dates, assignees
- [ ] Claim-text indexing (abstracts only today)
- [ ] Paper search

### Known limits

- The corpus is **BIGPATENT abstracts**, which carry no patent numbers, titles,
  or dates. Reference titles are derived from the abstract's first sentence and
  `patent_id` is a corpus index, not a real publication number. Wiring a real
  metadata source is the next meaningful step.
- Coverage is judged from abstracts, not full claim text. An abstract can omit
  something the claims teach, so `absent` means "not in this abstract".
- Not a freedom-to-operate opinion and not legal advice.

---

Adarsh Jha · 2026
