"""
One-time setup: creates the `patents` collection in Qdrant.

Run from the project root with the venv active:
    python scripts/init_collection.py

Idempotent: if the collection exists it prints its state and exits cleanly,
and also verifies the existing vector width matches what the embedding model
actually produces — a mismatch there fails every upsert with an opaque error,
so it is worth catching here.

    --recreate   drop and rebuild (DESTROYS all indexed data)
    --finalize   re-enable HNSW building after a bulk load, then wait for green

258,935 vectors at 1024 dims is 1.06 GB of float32 — over the Qdrant Cloud free
tier's whole 1 GB of RAM. on_disk + int8 quantization + on_disk_payload bring
that to ~500-600 MB resident and ~1.5 GB of disk. Local mode ignores all three.
"""

import argparse
import sys
import time
from pathlib import Path


from qdrant_client.models import (
    Distance,
    OptimizersConfigDiff,
    PayloadSchemaType,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    VectorParams,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "embeddings"))

from patently import config  # noqa: E402
from patently.retrieval import Store  # noqa: E402

DISTANCE = Distance.COSINE  # vectors are normalised, so cosine == dot product

# Qdrant's default. Restored by --finalize after a bulk load has run with the
# threshold at 0 (see build_index.py) so the graph is built once at the end
# rather than incrementally on 0.5 vCPU.
DEFAULT_INDEXING_THRESHOLD = 20_000


def set_indexing_threshold(client, name: str, threshold: int) -> None:
    """
    Set to 0 during a bulk load so index building doesn't compete with the
    upserts for the only half-core there is; --finalize restores it.
    """
    client.update_collection(
        collection_name=name,
        optimizers_config=OptimizersConfigDiff(indexing_threshold=threshold),
    )


def finalize(client, name: str) -> None:
    """Restore normal indexing and block until the graph is built."""
    info = client.get_collection(name)
    print(f"Collection '{name}': {info.points_count:,} points, "
          f"status={info.status}")
    threshold = DEFAULT_INDEXING_THRESHOLD
    print(f"Restoring indexing_threshold to {threshold:,}...")
    try:
        set_indexing_threshold(client, name, threshold)
    except Exception as exc:
        # A slow cluster often applies the change then times out answering.
        print(f"  (update call raised {type(exc).__name__}; checking whether it "
              "applied anyway)")
        current = client.get_collection(name).config.optimizer_config.indexing_threshold
        if current != threshold:
            raise
        print("  it applied.")

    print("Building HNSW graph. On the free tier this takes a while — "
          "safe to Ctrl-C,\nthe build continues server-side.")
    started = time.time()
    while True:
        info = client.get_collection(name)
        mins = (time.time() - started) / 60
        indexed = info.indexed_vectors_count or 0
        total = info.points_count or 0
        print(f"  [{mins:5.1f} min] status={info.status} "
              f"indexed={indexed:,}/{total:,}", flush=True)

        # Status alone is not the signal — a collection loaded with threshold 0
        # sits at "green" with nothing indexed. Nor is indexed == total, which
        # never happens: Qdrant leaves sub-threshold segments unindexed by
        # design. So: green, with at most one small segment outstanding.
        remainder = total - indexed
        if total and indexed > 0 and remainder <= threshold \
                and str(info.status).endswith("green"):
            print(f"\nDone in {mins:.1f} min. {indexed:,} vectors in the HNSW "
                  f"graph; {remainder:,} in a sub-threshold segment that Qdrant "
                  "searches exhaustively by design.")
            return
        time.sleep(15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop the collection if it exists, then recreate. DESTRUCTIVE.",
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="After a bulk load: restore the indexing threshold so Qdrant "
             "builds the HNSW graph, then wait for the collection to go green.",
    )
    args = parser.parse_args()

    store = Store.from_env()
    if store is None:
        print("ERROR: set QDRANT_URL (cloud) or QDRANT_PATH (local) in .env",
              file=sys.stderr)
        sys.exit(1)
    client = store.client
    name = config.COLLECTION
    exists = client.collection_exists(name)

    if args.finalize:
        if not exists:
            print(f"ERROR: collection '{name}' does not exist.", file=sys.stderr)
            sys.exit(1)
        finalize(client, name)
        return

    if exists and args.recreate:
        info = client.get_collection(name)
        print(f"About to DELETE '{name}' and its {info.points_count:,} points.")
        if input("Type the collection name to confirm: ").strip() != name:
            print("Aborted.")
            sys.exit(1)
        client.delete_collection(name)
        exists = False

    if exists:
        info = client.get_collection(name)
        size = info.config.params.vectors.size
        print(f"Collection '{name}' already exists.")
        print(f"  points:      {info.points_count:,}")
        print(f"  vector size: {size}")
        print(f"  distance:    {info.config.params.vectors.distance}")
        if size != config.VECTOR_SIZE:
            print(
                f"\nWARNING: this collection is {size}-dim but "
                f"{config.EMBED_MODEL} produces {config.VECTOR_SIZE}-dim "
                "vectors. Indexing into it will fail. Run with --recreate.",
                file=sys.stderr,
            )
            sys.exit(2)
        print("Pass --recreate to drop and rebuild.")
        return

    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(
            size=config.VECTOR_SIZE,
            distance=DISTANCE,
            # Memory-map the float32 originals. They are only read to rescore
            # the shortlist the quantized index already produced, so paging
            # them costs far less than the 1.06 GB of RAM holding them would.
            on_disk=True,
        ),
        # The int8 copy is the working index and is the one thing deliberately
        # pinned to RAM: 265 MB, versus 1.06 GB for the originals.
        quantization_config=ScalarQuantization(
            scalar=ScalarQuantizationConfig(
                type=ScalarType.INT8,
                quantile=0.99,  # clip outlier dims so the int8 range isn't wasted
                always_ram=True,
            )
        ),
        on_disk_payload=True,
    )
    # Indexed so CPC-scoped search stays fast once more than one subset is
    # loaded; without it Qdrant full-scans the payload to filter. Local
    # embedded mode has no payload indexes and warns if asked for one.
    if store.mode == "cloud":
        client.create_payload_index(
            collection_name=name,
            field_name="cpc",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    print(f"Created collection '{name}'")
    print(f"  vector size: {config.VECTOR_SIZE}")
    print(f"  distance:    {DISTANCE}")
    print(f"  mode:        {store.mode}")
    if store.mode == "cloud":
        print("  storage:     vectors on disk, int8 quantization pinned to RAM, "
              "payload on disk")
        print("\nEstimated at full corpus (258,935 abstracts): ~265 MB RAM for the "
              "quantized\nindex, ~1.5 GB disk. Fits the free tier's 1 GB / 4 GB.")
    else:
        print("  storage:     local embedded mode — on-disk/quantization "
              "settings do not apply")


if __name__ == "__main__":
    main()
