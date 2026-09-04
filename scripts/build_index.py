"""
Stream the BIGPATENT corpus, embed abstracts with bert-for-patents, and upsert
into Qdrant in batches.

BIGPATENT is organised by CPC category as subset names ("a" through "h" + "y").
Subset "g" is Physics/CS and includes the G06* software patents we target.
Per record: {"description": str, "abstract": str}.

Resume is by stream position: BIGPATENT streams deterministically in order, so
the index of the last processed record is all the state we need. (The earlier
version tracked a truncated set of seen ids instead, which could not survive a
corpus larger than the 50k it kept.)

Usage:
    python scripts/build_index.py --limit 1000   # smoke test first
    python scripts/build_index.py                # full run, resumes automatically
    python scripts/build_index.py --fresh        # ignore the checkpoint
"""

import argparse
import itertools
import json
import os
import signal
import sys
import time
from pathlib import Path

from datasets import load_dataset
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "embeddings"))
load_dotenv(ROOT / ".env")

from patently import config  # noqa: E402
from patently.retrieval import Embedder, Store, stable_point_id  # noqa: E402

CHECKPOINT_PATH = ROOT / ".checkpoint.json"

DATASET = os.getenv("PATENTLY_DATASET", "big_patent")
DATASET_CONFIG = os.getenv("PATENTLY_DATASET_CONFIG", "g")

EMBED_BATCH = 32
QDRANT_BATCH = 256
CHECKPOINT_EVERY = 10  # embed batches between checkpoint writes
MIN_ABSTRACT_CHARS = 100


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


def install_term_handler() -> None:
    """
    Route SIGTERM through the same graceful path as Ctrl-C.

    A full index run is hours long, so it will eventually be stopped by
    something that is not a keyboard: a `kill`, a container shutdown, a
    systemd restart. Without this, SIGTERM kills the process outright and the
    embeddings computed since the last checkpoint are simply lost.
    """

    def handler(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, handler)


def main():
    install_term_handler()
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap records processed in THIS run (for testing).")
    parser.add_argument("--fresh", action="store_true",
                        help="Ignore the checkpoint and start from record 0.")
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

    print(f"[model] loading {config.EMBED_MODEL}...")
    embedder = Embedder()
    print(f"[model] ready on {embedder.device}, dim={embedder.dim}")

    print(f"[dataset] streaming {DATASET} (subset: {DATASET_CONFIG})...")
    ds = load_dataset(DATASET, DATASET_CONFIG, split="train", streaming=True)
    # islice skips already-processed records without decoding them, which is
    # what makes resume cheap instead of a full re-embed.
    stream = itertools.islice(ds, start_index, None)

    embed_buffer: list[dict] = []
    upsert_buffer: list[PointStruct] = []
    batches_since_checkpoint = 0

    def flush_embeddings() -> int:
        if not embed_buffer:
            return 0
        vectors = embedder.encode([p["abstract"] for p in embed_buffer],
                                  batch_size=EMBED_BATCH)
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
            qdrant.upsert(collection_name=config.COLLECTION, points=upsert_buffer)
            upsert_buffer.clear()

    pbar = tqdm(desc="patents", unit="pat", initial=start_index)
    started = time.time()
    processed_this_run = 0

    try:
        for offset, record in enumerate(stream):
            if args.limit is not None and processed_this_run >= args.limit:
                break

            index = start_index + offset
            processed_this_run += 1
            state["processed"] += 1
            pbar.update(1)

            abstract = (record.get("abstract") or "").strip()
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
        save_checkpoint(state)
        print(f"[interrupt] safe to resume — rerun to continue from record "
              f"{state['next_index']:,}.")
        sys.exit(130)
    finally:
        pbar.close()

    elapsed = time.time() - started
    print(f"\n[done] processed={state['processed']:,} indexed={state['indexed']:,} "
          f"skipped={state['skipped']:,} in {elapsed / 60:.1f} min")


if __name__ == "__main__":
    main()
