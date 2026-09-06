# Deploying Patently

```
browser ──► Vercel (Next.js)  ──►  Hugging Face Space (FastAPI + BERT-Large)
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

That rules out Vercel functions (250 MB), Cloudflare Workers, and most free
containers (Render's free tier is 512 MB). The service needs ~2.5 GB of RAM and
a container that stays warm enough to be useful.

**Hugging Face Spaces, CPU Basic** is the recommendation: free, 2 vCPU, 16 GB
RAM, native Docker, and the model already lives on their CDN. Caveat worth
knowing — HF's pricing page lists CPU Basic as free but doesn't state
unambiguously whether Docker Spaces run on it, so confirm when you create the
Space. If it turns out to need a paid tier, **Google Cloud Run** is the fallback:
scales to zero, generous free tier, 2 GB+ RAM available, same image, cold start
in the 30-60s range because it pulls a ~3 GB image.

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

## 3. The service → Hugging Face Space

Create a **Docker** Space, then push this directory as its repo root — the
frontmatter in `embeddings/README.md` supplies `sdk: docker` and `app_port`.

```bash
# from the repo root
git subtree push --prefix embeddings hf main
```

where `hf` is the Space remote:

```bash
git remote add hf https://huggingface.co/spaces/<user>/patently-service
```

Then set these in **Settings → Variables and secrets**:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | your key |
| `QDRANT_URL` | your cluster URL |
| `QDRANT_API_KEY` | your cluster key |
| `DATABASE_URL` | from step 2, if using it |

**Do not set `QDRANT_PATH`.** It takes precedence over `QDRANT_URL` and would
point the service at a local store that doesn't exist in the container.

First build takes several minutes — it installs CPU-only torch and bakes the
1.3 GB model into the image so cold starts are a disk read rather than a
download. Confirm with:

```bash
curl https://<user>-patently-service.hf.space/health
```

`indexed_points` should read 258933.

## 4. The web app → Vercel

Import the repo, then:

| Setting | Value |
|---|---|
| Root directory | `web` |
| Framework | Next.js (auto-detected) |
| Env var `EMBEDDINGS_URL` | `https://<user>-patently-service.hf.space` |

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

- **The Space sleeps when idle.** The first request after that takes a minute or
  so to wake. The proxy times out at 55s with a message saying to try again
  rather than hanging.
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
