"""
One-time setup: creates the `patents` collection in Qdrant.

Run from the project root with the venv active:
    python scripts/init_collection.py

Idempotent: if the collection exists it prints its state and exits cleanly,
and also verifies the existing vector width matches what the embedding model
actually produces — a mismatch there fails every upsert with an opaque error,
so it is worth catching here.

Pass --recreate to drop and rebuild it (DESTROYS all indexed data).
"""

import argparse
import sys
from pathlib import Path


from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    VectorParams,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "embeddings"))

from patently import config  # noqa: E402
from patently.retrieval import Store  # noqa: E402

DISTANCE = Distance.COSINE  # vectors are normalised, so cosine == dot product


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop the collection if it exists, then recreate. DESTRUCTIVE.",
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
        vectors_config=VectorParams(size=config.VECTOR_SIZE, distance=DISTANCE),
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


if __name__ == "__main__":
    main()
