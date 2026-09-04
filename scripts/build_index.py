"""
Embed the BIGPATENT corpus and upsert it into Qdrant.

BIGPATENT is organised by CPC category as subset names ("a" through "h" + "y").
Subset "g" is Physics/CS and includes the G06* software patents we target.
Per record: {"description": str, "abstract": str}.

Usage:
    python scripts/build_index.py --limit 1000   # smoke test first
    python scripts/build_index.py                # full run, resumes automatically
    python scripts/build_index.py --fresh        # ignore the checkpoint

WHY THIS READS PARQUET DIRECTLY
-------------------------------
The obvious implementation is `load_dataset(..., streaming=True)`, and that is
what this script used to do. Two things make it the wrong tool here:

1. It reads whole rows. BIGPATENT's `description` column is the full patent
   specification and we discard it — but streaming still pays for it. Measured
   on one `g` shard: `description` is 13.1 MB compressed per row group against
   0.4 MB for `abstract`. Reading only the column we use cuts the transfer for
   subset `g` from roughly 3.5 GB to about 100 MB.

2. Resume was O(n) in what had already been done. `islice(ds, start_index, ...)`
   re-downloads and decodes every record before the resume point. Restarting a
   run at record 200,000 meant pulling ~2.7 GB before embedding anything.

Parquet is columnar and carries row counts in its footer, so we can project the
one column we need and skip whole shards after reading a few KB of metadata.
Resuming is then constant-time regardless of how far in we are.

Global row index is preserved across both readers: shards are read in sorted
filename order, which is the order `datasets` streams them in, so `patent_id`
values stay stable for anything already indexed. `--verify-resume` (on by
default when resuming) proves this against the live collection rather than
trusting it.

SURVIVING A SLEEPING MACHINE
----------------------------
A full run is a couple of hours of near-continuous GPU work, which is longer
than the default idle-sleep timer. On macOS the script holds a `caffeinate` assertion tied to its
own PID for as long as it runs. Note that preventing *system* sleep only works
on AC power — on battery macOS will still suspend, and the run resumes from the
last checkpoint when you wake it.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq
from dotenv import load_dotenv
from huggingface_hub import HfFileSystem
from qdrant_client.models import PointStruct
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "embeddings"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")

from init_collection import DEFAULT_INDEXING_THRESHOLD, set_indexing_threshold  # noqa: E402
from patently import config  # noqa: E402
from patently.retrieval import Embedder, Store, stable_point_id  # noqa: E402

CHECKPOINT_PATH = ROOT / ".checkpoint.json"

DATASET_REPO = os.getenv("PATENTLY_DATASET_REPO", "NortheasternUniversity/big_patent")
DATASET_CONFIG = os.getenv("PATENTLY_DATASET_CONFIG", "g")

EMBED_BATCH = 32
QDRANT_BATCH = 256
CHECKPOINT_EVERY = 10  # embed batches between checkpoint writes
MIN_ABSTRACT_CHARS = 100
UPSERT_ATTEMPTS = 5


# ---- checkpointing ---------------------------------------------------------


def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        state = json.loads(CHECKPOINT_PATH.read_text())
        # Tolerate the old checkpoint shape, which tracked `seen_ids` and had
        # no stream position. Its ids were generated with a per-process-salted
        # hash() and cannot be reproduced, so the only safe reading is to
        # resume from where `processed` says we got to.
        state.setdefault("next_index", state.get("processed", 0))
        state.pop("seen_ids", None)
        return state
    return {"next_index": 0, "processed": 0, "indexed": 0, "skipped": 0}


def save_checkpoint(state: dict) -> None:
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(CHECKPOINT_PATH)  # atomic: a killed run never leaves a torn file


# ---- corpus ----------------------------------------------------------------


def shard_paths(fs: HfFileSystem) -> list[str]:
    """Train shards for the configured subset, in the canonical read order."""
    pattern = f"datasets/{DATASET_REPO}/{DATASET_CONFIG}/train-*.parquet"
    paths = sorted(fs.glob(pattern))
    if not paths:
        raise RuntimeError(
            f"no train shards found for subset '{DATASET_CONFIG}' at {pattern}"
        )
    return paths


def iter_abstracts(fs: HfFileSystem, start_index: int):
    """
    Yield `(global_index, abstract)` from `start_index` onward.

    Only the `abstract` column is fetched, and shards or row groups that end
    before `start_index` are skipped after reading their footer alone — no
    column data for them crosses the network.
    """
    idx = 0
    for path in shard_paths(fs):
        with fs.open(path, "rb") as handle:
            pf = pq.ParquetFile(handle)
            if idx + pf.metadata.num_rows <= start_index:
                idx += pf.metadata.num_rows  # whole shard already done
                continue

            for rg in range(pf.metadata.num_row_groups):
                rows = pf.metadata.row_group(rg).num_rows
                if idx + rows <= start_index:
                    idx += rows
                    continue
                column = pf.read_row_group(rg, columns=["abstract"]).column("abstract")
                for abstract in column.to_pylist():
                    if idx >= start_index:
                        yield idx, abstract or ""
                    idx += 1


def read_at(fs: HfFileSystem, target: int) -> str | None:
    """Read one record by global index, for the resume alignment check."""
    for idx, abstract in iter_abstracts(fs, target):
        return abstract
    return None


def verify_alignment(fs: HfFileSystem, store: Store, start_index: int) -> None:
    """
    Confirm this reader's global indexing matches what is already in Qdrant.

    `patent_id` is `bp-<subset>-<global row index>`, so if the parquet read
    order ever diverged from the order the previous run used, the same abstract
    would be stored twice under two ids and the corpus would silently grow a
    duplicate of everything indexed so far. Cheaper to prove it than to trust
    it: two probes, one row group each.
    """
    probes = sorted({0, max(0, start_index // 2)})
    for probe in probes:
        expected = read_at(fs, probe)
        if expected is None:
            continue
        stored = store.client.retrieve(
            collection_name=config.COLLECTION,
            ids=[stable_point_id(f"bp-{DATASET_CONFIG}-{probe}")],
            with_payload=True,
        )
        if not stored:
            continue  # skipped as too short, or never reached — not evidence of drift
        actual = (stored[0].payload or {}).get("abstract", "")
        if actual.strip()[:200] != expected.strip()[:200]:
            print(
                f"\nERROR: record {probe} in the corpus does not match what is "
                f"stored under bp-{DATASET_CONFIG}-{probe}.\nThe parquet read "
                "order differs from the run that produced the existing index, "
                "so resuming\nwould duplicate the corpus under shifted ids. "
                "Rebuild from scratch:\n"
                "  python scripts/init_collection.py --recreate\n"
                "  python scripts/build_index.py --fresh",
                file=sys.stderr,
            )
            sys.exit(1)
    print(f"[verify] resume alignment confirmed at {probes}")


def derive_title(abstract: str) -> str:
    """
    BIGPATENT carries no title field, so we synthesise a display label from the
    first sentence of the abstract rather than a blind character slice, which
    used to cut words in half.
    """
    flat = " ".join(abstract.split())
    cut = flat.find(". ")
    head = flat[: cut + 1] if 0 < cut < 160 else flat[:140]
    return head.rstrip(" ,;:") + ("..." if len(head) < len(flat) else "")


# ---- process hygiene -------------------------------------------------------


def install_term_handler() -> None:
    """
    Route SIGTERM through the same graceful path as Ctrl-C.

    A full index run is long, so it will eventually be stopped by something
    that is not a keyboard: a `kill`, a container shutdown, a systemd restart.
    Without this, SIGTERM kills the process outright and the embeddings
    computed since the last checkpoint are simply lost.
    """

    def handler(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, handler)


def prevent_sleep() -> subprocess.Popen | None:
    """
    Keep the machine awake for exactly as long as this process lives.

    `-w <pid>` ties the assertion to our PID, so the helper exits when we do
    even if we are killed — no stray process left holding the machine awake.
    `-s` (prevent system sleep) is only honoured on AC power; on battery the
    machine still sleeps and the run picks up from the last checkpoint.
    """
    if sys.platform != "darwin":
        return None
    try:
        return subprocess.Popen(
            ["caffeinate", "-i", "-m", "-s", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        return None


def upsert_with_retry(qdrant, points: list[PointStruct]) -> None:
    """
    Retry an upsert with exponential backoff.

    An hour-long run against a hosted cluster will hit a transient network
    error or a rate limit eventually. Without this, one blip discards every
    embedding computed since the last checkpoint.
    """
    for attempt in range(UPSERT_ATTEMPTS):
        try:
            qdrant.upsert(collection_name=config.COLLECTION, points=points)
            return
        except Exception as exc:
            if attempt == UPSERT_ATTEMPTS - 1:
                raise
            wait = 2**attempt
            print(
                f"\n[retry] upsert failed ({type(exc).__name__}: {exc}); "
                f"retrying in {wait}s "
                f"[{attempt + 1}/{UPSERT_ATTEMPTS - 1}]",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(wait)


# ---- main ------------------------------------------------------------------


def main():
    install_term_handler()
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap records processed in THIS run (for testing).")
    parser.add_argument("--fresh", action="store_true",
                        help="Ignore the checkpoint and start from record 0.")
    parser.add_argument("--fp32", action="store_true",
                        help="Embed in float32. Default is fp16, which is 2.75x "
                             "faster on MPS with equivalent vectors.")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip the resume alignment check.")
    parser.add_argument("--no-bulk-tuning", action="store_true",
                        help="Leave the collection's indexing threshold alone.")
    parser.add_argument("--throttle", type=float, default=0.0, metavar="SECONDS",
                        help="Idle the GPU for this long after each embed batch. "
                             "Lowers sustained load and heat at the cost of wall "
                             "clock: with a batch taking ~1.1s, --throttle 1.1 "
                             "halves the duty cycle and doubles the runtime. "
                             "Default 0 (full speed).")
    args = parser.parse_args()

    if args.fresh and CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
    state = load_checkpoint()
    start_index = state["next_index"]
    print(f"[checkpoint] resuming at record {start_index:,} "
          f"(indexed={state['indexed']:,} skipped={state['skipped']:,})")

    store = Store.from_env()
    if store is None:
        print("ERROR: set QDRANT_URL (cloud) or QDRANT_PATH (local) in .env",
              file=sys.stderr)
        sys.exit(1)
    qdrant = store.client
    if not qdrant.collection_exists(config.COLLECTION):
        print(f"ERROR: collection '{config.COLLECTION}' not found. "
              "Run scripts/init_collection.py first.", file=sys.stderr)
        sys.exit(1)

    keep_awake = prevent_sleep()
    if keep_awake:
        print("[power] holding a caffeinate assertion for this process "
              "(system sleep is only deferred on AC power)")

    fs = HfFileSystem()
    if start_index > 0 and not args.no_verify:
        verify_alignment(fs, store, start_index)

    print(f"[model] loading {config.EMBED_MODEL}...")
    embedder = Embedder(half=not args.fp32)
    print(f"[model] ready on {embedder.device}, dim={embedder.dim}, "
          f"precision={'fp32' if args.fp32 else 'fp16'}")
    if args.throttle:
        print(f"[power] throttling: {args.throttle}s idle after every "
              f"{EMBED_BATCH}-abstract batch")

    # On a 0.5 vCPU cluster, building the HNSW graph while points stream in
    # competes with the upserts for the only core available. Turn it off for
    # the load and build once at the end via `init_collection.py --finalize`.
    bulk_tuned = False
    if store.mode == "cloud" and not args.no_bulk_tuning:
        set_indexing_threshold(qdrant, config.COLLECTION, 0)
        bulk_tuned = True
        print("[qdrant] indexing paused for bulk load")

    print(f"[dataset] reading {DATASET_REPO} subset '{DATASET_CONFIG}' "
          "(abstract column only)")

    embed_buffer: list[dict] = []
    upsert_buffer: list[PointStruct] = []
    batches_since_checkpoint = 0

    def flush_embeddings() -> int:
        if not embed_buffer:
            return 0
        vectors = embedder.encode([p["abstract"] for p in embed_buffer],
                                  batch_size=EMBED_BATCH)
        if args.throttle:
            # Duty-cycling rather than clock-limiting: the GPU still runs flat
            # out during a batch, but idles between them, so average power (and
            # therefore steady-state temperature) drops roughly in proportion.
            # Total energy for the run is close to unchanged — this trades peak
            # temperature for time under load, which is the trade you want when
            # the machine is on a lap or the fan noise is the problem.
            time.sleep(args.throttle)
        for p, vec in zip(embed_buffer, vectors):
            upsert_buffer.append(PointStruct(
                id=p["qdrant_id"],
                vector=vec,
                payload={
                    "patent_id": p["patent_id"],
                    "title": p["title"],
                    "abstract": p["abstract"],
                    "cpc": DATASET_CONFIG,
                },
            ))
        n = len(embed_buffer)
        embed_buffer.clear()
        return n

    def flush_upserts() -> None:
        if upsert_buffer:
            upsert_with_retry(qdrant, upsert_buffer)
            upsert_buffer.clear()

    pbar = tqdm(desc="patents", unit="pat", initial=start_index)
    started = time.time()
    processed_this_run = 0
    index = start_index - 1

    try:
        for index, abstract in iter_abstracts(fs, start_index):
            if args.limit is not None and processed_this_run >= args.limit:
                break

            processed_this_run += 1
            state["processed"] += 1
            pbar.update(1)

            abstract = (abstract or "").strip()
            if len(abstract) < MIN_ABSTRACT_CHARS:
                state["skipped"] += 1
                state["next_index"] = index + 1
                continue

            patent_id = f"bp-{DATASET_CONFIG}-{index}"
            embed_buffer.append({
                "qdrant_id": stable_point_id(patent_id),
                "patent_id": patent_id,
                "title": derive_title(abstract),
                "abstract": abstract,
            })

            if len(embed_buffer) >= EMBED_BATCH:
                state["indexed"] += flush_embeddings()  # count what actually flushed
                batches_since_checkpoint += 1

                if len(upsert_buffer) >= QDRANT_BATCH:
                    flush_upserts()

                if batches_since_checkpoint >= CHECKPOINT_EVERY:
                    # Flush before checkpointing so the saved position never
                    # runs ahead of what Qdrant actually holds — otherwise a
                    # crash between the two leaves a permanent gap in the index.
                    flush_upserts()
                    state["next_index"] = index + 1
                    save_checkpoint(state)
                    batches_since_checkpoint = 0
                    elapsed = time.time() - started
                    pbar.set_postfix(
                        indexed=state["indexed"],
                        skipped=state["skipped"],
                        rate=f"{processed_this_run / max(elapsed, 1e-9):.1f}/s",
                    )

            state["next_index"] = index + 1

        state["indexed"] += flush_embeddings()
        flush_upserts()
        save_checkpoint(state)

    except KeyboardInterrupt:
        print("\n[interrupt] flushing buffers and saving checkpoint...")
        state["indexed"] += flush_embeddings()
        flush_upserts()
        state["next_index"] = index + 1
        save_checkpoint(state)
        print(f"[interrupt] safe to resume — rerun to continue from record "
              f"{state['next_index']:,}.")
        # Deliberately not restoring the indexing threshold: the load is not
        # finished, and re-enabling it now would build a graph we are about to
        # invalidate with more points.
        sys.exit(130)
    finally:
        pbar.close()
        if keep_awake:
            keep_awake.terminate()

    elapsed = time.time() - started
    print(f"\n[done] processed={state['processed']:,} indexed={state['indexed']:,} "
          f"skipped={state['skipped']:,} in {elapsed / 60:.1f} min")

    if bulk_tuned:
        print(
            f"\nIndexing is still paused on '{config.COLLECTION}'. Build the "
            f"HNSW graph with:\n  python scripts/init_collection.py --finalize\n"
            f"(this restores indexing_threshold to "
            f"{DEFAULT_INDEXING_THRESHOLD:,} and waits for the collection to "
            "go green)"
        )


if __name__ == "__main__":
    main()
