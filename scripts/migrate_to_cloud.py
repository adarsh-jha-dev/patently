"""
Copy an already-built local collection into a Qdrant Cloud cluster.

Embedding is the expensive step and it is already paid for by the time this
runs, so moving to a hosted cluster is a transfer rather than a rebuild. The
directory cannot just be copied — local mode is a single SQLite file, not the
format a server reads — so points are scrolled out with their vectors and
upserted in batches.

Safe to re-run: point ids are blake2b digests identical on both sides, so an
upsert overwrites rather than duplicates, and the scroll offset is checkpointed.

Order matters — quantization and on-disk storage can only be set at creation:

    1. python scripts/init_collection.py      (against the CLOUD target)
    2. python scripts/migrate_to_cloud.py
    3. python scripts/init_collection.py --finalize

Usage:
    python scripts/migrate_to_cloud.py --dry-run   # count and estimate only
    python scripts/migrate_to_cloud.py
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "embeddings"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")

from init_collection import DEFAULT_INDEXING_THRESHOLD, set_indexing_threshold  # noqa: E402
from patently import config  # noqa: E402

CHECKPOINT_PATH = ROOT / ".migrate_checkpoint.json"

SCROLL_BATCH = 256
UPSERT_ATTEMPTS = 5


def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text())
    return {"offset": None, "sent": 0}


def save_checkpoint(state: dict) -> None:
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, default=str))
    tmp.replace(CHECKPOINT_PATH)


def open_source(path: str) -> QdrantClient:
    """
    Takes the same exclusive lock the indexer uses, so build_index.py must not
    be running.
    """
    if not Path(path).exists():
        print(f"ERROR: no local store at {path}", file=sys.stderr)
        sys.exit(1)
    return QdrantClient(path=path)


def open_target() -> QdrantClient:
    """
    gRPC, not REST: Qdrant's REST API is JSON, so a 1024-dim vector ships as
    20,764 bytes of decimal text against 4,096 binary. Measured 36 pts/sec over
    REST versus 97 over gRPC — the transfer is bandwidth-bound.
    """
    url = os.getenv("QDRANT_URL")
    key = os.getenv("QDRANT_API_KEY")
    if not url:
        print("ERROR: set QDRANT_URL (and QDRANT_API_KEY) in .env — that is the "
              "cloud target this copies into.", file=sys.stderr)
        sys.exit(1)
    return QdrantClient(url=url, api_key=key, timeout=300, prefer_grpc=True)


def upsert_with_retry(
    client: QdrantClient, points: list[PointStruct], collection: str | None = None
) -> None:
    for attempt in range(UPSERT_ATTEMPTS):
        try:
            client.upsert(
                collection_name=collection or config.COLLECTION, points=points
            )
            return
        except Exception as exc:
            if attempt == UPSERT_ATTEMPTS - 1:
                raise
            wait = 2**attempt
            print(f"\n[retry] upsert failed ({type(exc).__name__}: {exc}); "
                  f"retrying in {wait}s", file=sys.stderr, flush=True)
            time.sleep(wait)


def copy_points(
    source: QdrantClient,
    target: QdrantClient,
    collection: str,
    batch: int,
    state: dict,
    on_batch=None,
    checkpoint=save_checkpoint,
) -> dict:
    """
    Scroll every point out of `source` and upsert it into `target`.

    Split out from main() so the round-trip fidelity of the vectors is testable
    without a cluster. `state` carries the resume offset, checkpointed per batch.
    """
    offset = state.get("offset")
    while True:
        points, next_offset = source.scroll(
            collection_name=collection,
            limit=batch,
            offset=offset,
            with_payload=True,
            with_vectors=True,  # the whole point of the exercise
        )
        if not points:
            break

        upsert_with_retry(target, [
            PointStruct(id=p.id, vector=p.vector, payload=p.payload)
            for p in points
        ], collection=collection)
        state["sent"] = state.get("sent", 0) + len(points)
        state["offset"] = next_offset
        checkpoint(state)
        if on_batch is not None:
            on_batch(len(points))

        offset = next_offset
        if offset is None:
            break
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=os.getenv("QDRANT_PATH", "./.qdrant"),
                        help="Local store directory (default: QDRANT_PATH).")
    parser.add_argument("--batch", type=int, default=SCROLL_BATCH,
                        help="Points per scroll/upsert round trip.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report sizes and estimates, transfer nothing.")
    parser.add_argument("--fresh", action="store_true",
                        help="Ignore the migration checkpoint and start over. "
                             "Safe: upserts overwrite by id.")
    parser.add_argument("--no-bulk-tuning", action="store_true",
                        help="Leave the target's indexing threshold alone.")
    args = parser.parse_args()

    source_path = str((ROOT / args.source).resolve())
    source = open_source(source_path)
    total = source.get_collection(config.COLLECTION).points_count or 0

    dim = config.VECTOR_SIZE
    # 4 bytes per float32 dimension, plus the measured mean payload size. This
    # is the gRPC (binary) figure — over REST the same data is ~5x larger,
    # which is exactly why open_target() does not use REST.
    approx_bytes = total * (dim * 4 + 950)
    print(f"source : {source_path}")
    print(f"points : {total:,}")
    print(f"payload: ~{approx_bytes / 1e9:.2f} GB to transfer over gRPC "
          f"({dim}-dim float32 + payload); ~{approx_bytes * 5.1 / 1e9:.1f} GB "
          "if this used REST")

    if args.dry_run:
        print("\n--dry-run: nothing transferred.")
        print("Re-embedding this corpus would cost hours of GPU time; this "
              "transfer is network-bound instead.")
        source.close()
        return

    target = open_target()
    if not target.collection_exists(config.COLLECTION):
        print(f"\nERROR: collection '{config.COLLECTION}' does not exist on the "
              "target.\nCreate it first so the on-disk + int8 storage config is "
              "applied:\n  QDRANT_PATH= python scripts/init_collection.py",
              file=sys.stderr)
        sys.exit(1)

    already = target.get_collection(config.COLLECTION).points_count or 0
    print(f"target : {os.getenv('QDRANT_URL')}")
    print(f"         holds {already:,} points before this run")

    if args.fresh and CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
    state = load_checkpoint()
    offset = state["offset"]
    if offset is not None:
        print(f"[checkpoint] resuming after {state['sent']:,} points already sent")

    bulk_tuned = False
    if not args.no_bulk_tuning:
        set_indexing_threshold(target, config.COLLECTION, 0)
        bulk_tuned = True
        print("[qdrant] indexing paused on the target for the bulk load")

    pbar = tqdm(total=total, initial=state["sent"], desc="points", unit="pt")
    started = time.time()
    try:
        copy_points(
            source, target, config.COLLECTION, args.batch, state,
            on_batch=pbar.update,
        )
    except KeyboardInterrupt:
        print(f"\n[interrupt] safe to resume — {state['sent']:,} points sent. "
              "Rerun to continue.")
        sys.exit(130)
    finally:
        pbar.close()
        source.close()

    elapsed = time.time() - started
    final = target.get_collection(config.COLLECTION).points_count or 0
    print(f"\n[done] sent {state['sent']:,} points in {elapsed / 60:.1f} min")
    print(f"       target now holds {final:,} (source has {total:,})")
    if final < total:
        print("       NOTE: target count is still catching up — Qdrant applies "
              "upserts asynchronously; re-check in a moment.")

    if bulk_tuned:
        print(f"\nIndexing is still paused. Build the HNSW graph with:\n"
              f"  QDRANT_PATH= python scripts/init_collection.py --finalize\n"
              f"(restores indexing_threshold to {DEFAULT_INDEXING_THRESHOLD:,})")


if __name__ == "__main__":
    main()
