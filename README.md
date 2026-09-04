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

## The guided form

A blank textarea asking someone to "describe your invention" is a bad interface
for the person who most needs this tool. It rewards people who already write
like a patent attorney and gives everyone else a worse search without telling
them why.

So the description sits alongside seven structured questions — technical field,
what form the invention takes, its key parts, its inputs and outputs, the
closest existing approach, the claimed novelty, and where it runs. Each one
changes the search: field and context set the vocabulary the query angles are
written in, form decides whether elements decompose as ordered steps or as
structural limitations, and the closest-existing-approach answer supplies the
angle the model is least able to infer on its own.

Every question also offers **"not sure"** (or "no idea"), and that is a real
answer rather than a skip. Analysis only runs once all of them carry a value,
so an incomplete form can't be submitted by accident — but never at the cost of
demanding knowledge the user doesn't have.

The important part is what happens next: fields marked "not sure" are dropped
before the prompt is built. They are *not* sent as "unknown", because telling a
model a value is unknown invites it to supply a plausible one, and a guessed
technical field silently narrows every query angle downstream of it. An omitted
field leaves the search deliberately broad on that axis, which is the correct
behaviour when nobody knows the answer.

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
python scripts/init_collection.py --finalize # cloud only: build the HNSW graph
```

The BIGPATENT "g" train split is **258,935 abstracts**. Measured on an M-series
Mac, fp16 encodes uniform-length text at ~76/sec against ~28/sec in fp32.

End-to-end throughput on the real corpus is lower — **~29/sec**, so a full build
is around **2.5 hours**. The gap is not the model: the loop is single-threaded,
so the GPU idles during parquet reads and Qdrant upserts, real abstracts run up
to `MAX_EMBED_CHARS` rather than the benchmark's uniform ~1000, and macOS holds
back sustained GPU clocks on battery power. Plug in for the full rate. fp16 is the default — cosine
similarity against the fp32 embedding of the same abstract is ≥ 0.9995 (mean
1.0000) and top-10 neighbour lists are unchanged, so the precision buys nothing
here. `--fp32` opts out.

Only the `abstract` column is read. `description` — the full patent
specification, which this project never uses — is 97% of the bytes on disk, so
projecting it away cuts the transfer for subset "g" from ~3.5 GB to ~100 MB.
Reading parquet directly also makes resume constant-time: shards that end
before the checkpoint are skipped after reading their footer, instead of being
re-downloaded and decoded.

A run holds a `caffeinate` assertion tied to its own PID, so the machine will
not idle-sleep mid-build (on AC power; on battery macOS still suspends and the
run resumes from the checkpoint). Interrupts, `SIGTERM` and network blips are
all safe — buffers flush, the checkpoint is atomic, and upserts retry with
backoff.

> Local embedded mode takes an exclusive lock on the directory — the indexer
> and the service can't hold it at the same time.

#### Fitting the Qdrant Cloud free tier

The free tier is 0.5 vCPU / 1 GB RAM / 4 GB disk. At 1024 dims, 258,935
float32 vectors are **1.06 GB — over the whole RAM budget before payloads or
the index are counted**. `init_collection.py` therefore creates the collection
with the vectors memory-mapped (`on_disk`), an int8 scalar-quantized copy
pinned to RAM (265 MB, and what actually serves search), and payloads on disk.
That lands around 500-600 MB resident and ~1.5 GB of disk. Search over-fetches
2x and rescores against the on-disk originals, so ranking matches an
unquantized collection.

During a bulk load `build_index.py` sets `indexing_threshold=0`, because
building the HNSW graph incrementally competes with the upserts for the only
half-core there is; `--finalize` restores it and waits for the collection to go
green. None of this applies to local embedded mode, which ignores all of it.

> Free clusters suspend after a week of inactivity and are deleted after four.

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
| `GET /analyses` | recent saved analyses (newest first) |
| `GET /analyses/{slug}` | one saved analysis, whole |

## Saved analyses

An analysis costs two model calls and 10-30s, and until now evaporated when the
tab closed. Set `DATABASE_URL` and every run is filed and gets a permalink at
`/a/<slug>`; leave it unset and nothing changes — persistence is a feature of
the service, never a requirement for running it. The table is created on
startup, so there is no migration step.

Two things about the schema are deliberate. The whole `AnalyzeResult` is stored
as JSONB rather than columns, because the result shape is still moving and a
migration per field would make changing the pipeline expensive in exactly the
phase where it should be cheap. And every row records the corpus it ran
against — `Inconclusive` over 8,220 abstracts and `Inconclusive` over 258,935
are completely different claims, and a row that cannot tell them apart is not
worth keeping. It is also what lets you re-run the same disclosure after a
bigger index build and show the verdict move.

## Tests

```bash
cd embeddings && python -m pytest tests/ -q
```

68 tests, no network and no API key required. They cover the parts that decide
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
- [x] Guided rubric form, with "not sure" as a first-class answer
- [x] Saved analyses with shareable permalinks
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
