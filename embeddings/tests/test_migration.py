"""
Tests for the local -> cloud migration.

The claim under test: vectors survive the scroll/upsert round trip unchanged,
so the corpus can move without re-embedding. If they came back truncated or
reordered the only symptom would be worse search results much later.

Run against two local stores, so no network or credentials are needed.

    cd embeddings && python -m pytest tests/ -q
"""

import sys
from pathlib import Path

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from migrate_to_cloud import copy_points  # noqa: E402

DIM = 32  # small enough to keep the test fast; the code is dimension-agnostic
COLLECTION = "patents"
N = 70  # deliberately not a multiple of the batch size


def make_store(path: Path) -> QdrantClient:
    client = QdrantClient(path=str(path))
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
    )
    return client


def seed(client: QdrantClient, n: int = N) -> list[PointStruct]:
    points = [
        PointStruct(
            id=1000 + i,
            vector=[(i * 0.01 + j * 0.001) for j in range(DIM)],
            payload={"patent_id": f"bp-g-{i}", "abstract": f"abstract {i}",
                     "cpc": "g"},
        )
        for i in range(n)
    ]
    client.upsert(collection_name=COLLECTION, points=points)
    return points


@pytest.fixture
def stores(tmp_path):
    src = make_store(tmp_path / "src")
    dst = make_store(tmp_path / "dst")
    yield src, dst
    src.close()
    dst.close()


def fetch_all(client: QdrantClient) -> dict:
    points, _ = client.scroll(
        COLLECTION, limit=1000, with_payload=True, with_vectors=True
    )
    return {p.id: p for p in points}


def test_every_point_is_copied(stores):
    src, dst = stores
    seed(src)
    state = copy_points(src, dst, COLLECTION, batch=16, state={},
                        checkpoint=lambda s: None)
    assert state["sent"] == N
    assert (dst.get_collection(COLLECTION).points_count or 0) == N


def test_vectors_survive_the_round_trip_exactly(stores):
    """If this fails, the migration silently degrades the index."""
    src, dst = stores
    seed(src)
    copy_points(src, dst, COLLECTION, batch=16, state={},
                checkpoint=lambda s: None)

    before, after = fetch_all(src), fetch_all(dst)
    assert set(before) == set(after), "point ids diverged"
    for pid, original in before.items():
        assert after[pid].vector == pytest.approx(original.vector, abs=1e-6), pid


def test_payloads_survive_the_round_trip(stores):
    src, dst = stores
    seed(src)
    copy_points(src, dst, COLLECTION, batch=16, state={},
                checkpoint=lambda s: None)

    before, after = fetch_all(src), fetch_all(dst)
    for pid, original in before.items():
        assert after[pid].payload == original.payload, pid


def test_ids_are_preserved_so_reruns_overwrite(stores):
    """
    Ids come from stable_point_id and must not be regenerated in transit —
    otherwise a re-run after a failure duplicates the whole corpus instead of
    overwriting it.
    """
    src, dst = stores
    seed(src)
    copy_points(src, dst, COLLECTION, batch=16, state={},
                checkpoint=lambda s: None)
    copy_points(src, dst, COLLECTION, batch=16, state={},
                checkpoint=lambda s: None)  # deliberately again

    assert (dst.get_collection(COLLECTION).points_count or 0) == N


def test_resume_from_checkpoint_does_not_resend(stores):
    """An interrupted transfer must continue, not restart."""
    src, dst = stores
    seed(src)

    # Stop after the first batch, exactly as an interrupt would.
    state: dict = {}
    saved: list[dict] = []

    def capture(s):
        saved.append(dict(s))
        if s["sent"] >= 16:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        copy_points(src, dst, COLLECTION, batch=16, state=state,
                    checkpoint=capture)

    partial = saved[-1]
    assert partial["sent"] == 16
    assert (dst.get_collection(COLLECTION).points_count or 0) == 16

    resumed = copy_points(
        src, dst, COLLECTION, batch=16, state=partial, checkpoint=lambda s: None
    )
    # Sent count continues from where it stopped rather than starting over.
    assert resumed["sent"] == N
    assert (dst.get_collection(COLLECTION).points_count or 0) == N


def test_empty_source_is_a_no_op(stores):
    src, dst = stores
    state = copy_points(src, dst, COLLECTION, batch=16, state={},
                        checkpoint=lambda s: None)
    assert state.get("sent", 0) == 0
    assert (dst.get_collection(COLLECTION).points_count or 0) == 0
