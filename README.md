# Patently

> Semantic prior art search for inventions. Describe what you're building in plain English; get back the patents and papers that might conflict.

## What it does

Most patent search tools are keyword-shaped — you need to know the right terminology to find anything. Patently flips that: you describe your invention in plain English/upload any files, an agent decomposes it into multiple search angles, runs semantic search across patents, and returns ranked potential conflicts with reasoning.

## How it works

```
description/files ──► agent decomposes into 4-6 search angles
            ──► parallel semantic search (patent-bert embeddings)
            ──► LLM re-ranks top candidates
            ──► report with reasoning per result
```

## Stack

- **web/** — Next.js 15, TypeScript, Tailwind, Shadcn
- **embeddings/** — Python, FastAPI, sentence-transformers (bert-for-patents)
- **Qdrant** for vector storage
- **Postgres** for metadata
- **Gemini / Anthropic** for the reasoning layer

## Status

In development. Currently building the embeddings pipeline.

Roadmap:
- [ ] Embeddings service (in progress)
- [ ] Patent corpus indexing (software patents 2018-2024, ~300k)
- [ ] Decomposition + re-ranking agent
- [ ] Web UI
- [ ] Multi-provider LLM support
- [ ] Paper search (v2)

---

Adarsh Jha · 2026