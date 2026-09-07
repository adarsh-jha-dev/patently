# Deploying Patently

```
browser ──► Vercel (Next.js)  ──►  Cloud Run (FastAPI + BERT-Large)
                                          │
                                          ├──► Qdrant Cloud   258,933 vectors
                                          └──► Neon Postgres  saved analyses
```

The browser only ever talks to Vercel. Every call to the Python service goes
through a Next.js route handler or a server component, so the service URL and
all API keys stay server-side.

## Why the service can't be serverless

The service loads `anferico/bert-for-patents` — BERT-Large, 1.3 GB of weights —
and **the vectors already in Qdrant were produced by that model**. Query vectors
must come from the same one, so it cannot be swapped for a hosted embedding API
without re-indexing the whole corpus.

That rules out Vercel functions (250 MB) and Cloudflare Workers. Measured
resident memory is ~580 MB idle and ~430 MB serving — well under the 1.3 GB of
weights, because safetensors are memory-mapped and never all resident at once.
That is still over Render's 512 MB free tier, but only just.

**Google Cloud Run.** Free at portfolio traffic (2M requests/month), scales to
zero, up to 32 GB RAM available, and it takes the `Dockerfile` unchanged.

Hugging Face was tried first and does not work. Docker Spaces require a paid
plan; Gradio on CPU Basic is also paid on a free account ("Static Spaces are
free"); and ZeroGPU — the only free compute — refuses to start a Space with no
`@spaces.GPU` function, which a CPU-only API will never have. The service ran
correctly inside HF's network (model loaded, Qdrant and Postgres connected) and
was rejected for the kind of workload it is, not for anything wrong with it.

Re-embedding the corpus through a hosted API would have shrunk the service
enough for a 512 MB free tier, but neither route works: HF's Inference API
refuses feature-extraction for this model (it is published as `fill-mask`), and
Gemini's embedding free tier measured **4 texts/sec sustained** — 18 hours for
258,933 abstracts.

---

## 1. Qdrant Cloud — done

258,933 points, HNSW built, int8 quantization pinned to RAM. Nothing to do.

> Free clusters **suspend after a week of inactivity and are deleted after
> four**. A portfolio demo nobody clicks for a month will die silently. If this
> matters, either open it periodically or move to a paid cluster.

## 2. Postgres (Neon) — optional but worth it

Without it the app works and simply doesn't save; with it, every analysis gets
a shareable permalink at `/a/<slug>`.

1. Create a free project at [neon.tech](https://neon.tech)
2. Copy the connection string — the `?sslmode=require` form is fine, it's
   translated for asyncpg automatically
3. Keep it for step 3

The table is created on first boot. There is no migration step.

## 3. The service → Cloud Run

> **Live:** https://patently-service-136023854508.asia-south1.run.app

Install the CLI (`brew install --cask google-cloud-sdk`), then:

```bash
gcloud auth login
gcloud config set project <your-project-id>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com

cd embeddings
gcloud run deploy patently-service \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 120 \
  --max-instances 2 \
  --set-env-vars "$(paste -sd, - <<'EOF'
GEMINI_API_KEY=...
QDRANT_URL=...
QDRANT_API_KEY=...
DATABASE_URL=...
EOF
)"
```

`--memory 2Gi` is deliberate headroom: measured peak is ~580 MB, but Cloud Run
kills an over-limit container with no useful error, and cgroup accounting can
charge memory-mapped pages differently than Docker's does. 2 GB costs nothing
extra at this traffic. `--max-instances 2` caps the blast radius if something
loops, and `--source .` lets Cloud Build build the image so there is no local
push.

Equivalent settings if you use the console instead:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | your key |
| `QDRANT_URL` | your cluster URL |
| `QDRANT_API_KEY` | your cluster key |
| `DATABASE_URL` | from step 2, if using it |

**Do not set `QDRANT_PATH`.** It takes precedence over `QDRANT_URL` and would
point the service at a local store that doesn't exist in the container.

First build takes several minutes — CPU-only torch, plus the 1.3 GB model baked
into the image so cold starts are a disk read rather than a download. Confirm
with:

```bash
curl https://<service-url>/health
```

`indexed_points` should read 258933.

## 4. The web app → Vercel

Import the repo, then:

| Setting | Value |
|---|---|
| Root directory | `web` |
| Framework | Next.js (auto-detected) |
| Env var `EMBEDDINGS_URL` | `https://patently-service-136023854508.asia-south1.run.app` |

That's the whole configuration. `maxDuration` is set to 60s in the analyze
route, which fits Vercel's Hobby ceiling and a 12-30s analysis.

---

## Cost control

`/analyze` spends two LLM calls per request against one shared key, so the
public deployment is rate limited by default:

| Limit | Default | Variable |
|---|---|---|
| Per client | 5 analyses/hour | `PATENTLY_RATE_LIMIT`, `PATENTLY_RATE_WINDOW` |
| Everyone, per UTC day | 200 analyses | `PATENTLY_DAILY_BUDGET` |

The daily budget is the one that actually bounds spend — a per-IP window alone
still lets a hundred clients drain the quota, and the IP itself comes from
`X-Forwarded-For`, which a determined caller can spoof. Both limits return 429
with `Retry-After`; the UI shows the message. `GET /health` reports live usage.

Limits are in-memory, so they're per-process and reset on redeploy. Fine for a
single container; if you ever run replicas, the effective limit multiplies.

## Known behaviour after deployment

- **Cloud Run scales to zero.** A request after idle pays a cold start while the
  ~3 GB image is pulled and the model loads — tens of seconds. The proxy times
  out at 55s with a message saying to try again rather than hanging. Set
  `--min-instances 1` to remove it, but that bills continuously.
- **Cloud search is 2-3× slower than local** (0.5-1.8s vs 0.2-0.5s per query).
  An analysis fires 4-6 in parallel, so expect retrieval around 3-6s of a
  12-30s total. The LLM calls dominate either way.
- **The corpus ends around 2014.** BIGPATENT contains no post-2014 art, so
  anything modern legitimately returns `Inconclusive`. That's the honesty guard
  working, not a bug — but it's worth saying on the page so a visitor testing it
  with a 2024 idea understands what they're seeing.
- **Analyses are not reproducible.** The same disclosure can produce different
  scores run to run; the variance starts at decomposition and Gemini exposes no
  seed.
