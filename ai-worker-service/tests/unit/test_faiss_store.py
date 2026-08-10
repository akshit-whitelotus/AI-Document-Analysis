"""
Run from ai-worker-service/:
    pytest tests/unit/test_faiss_store.py -q

These use a real FaissStore backed by a real (temporary) faiss index -
not a mock - because the owner_id filtering logic lives inside search()'s
interaction with the index and its metadata, which is exactly the thing
worth testing for real rather than assuming.
"""
from uuid import uuid4

import numpy as np
import pytest

from app.vectorstore.faiss_store import FaissStore, EMBEDDING_DIM


def unit_vector(hot_index: int) -> list[float]:
    """A simple one-hot unit vector, so inner-product search gives an
    unambiguous, deterministic ranking between vectors."""
    v = np.zeros(EMBEDDING_DIM, dtype="float32")
    v[hot_index] = 1.0
    return v.tolist()


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_search_never_returns_another_owners_chunks(owner_a, owner_b):
    store = FaissStore()
    doc_a, doc_b = uuid4(), uuid4()
    store.add(doc_a, ["owner A's private text"], [unit_vector(0)], owner_id=owner_a)
    store.add(doc_b, ["owner B's private text"], [unit_vector(0)], owner_id=owner_b)

    # Both documents have the *identical* vector, so without owner
    # filtering this query would return both - the whole point of the fix.
    results = store.search(unit_vector(0), owner_id=owner_a, top_k=10)

    assert len(results) == 1
    assert results[0]["document_id"] == str(doc_a)
    assert all(r["document_id"] != str(doc_b) for r in results)


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_document_ids_filter_still_applies_within_one_owner(owner_a):
    store = FaissStore()
    doc_1, doc_2 = uuid4(), uuid4()
    store.add(doc_1, ["chunk in doc 1"], [unit_vector(0)], owner_id=owner_a)
    store.add(doc_2, ["chunk in doc 2"], [unit_vector(1)], owner_id=owner_a)

    results = store.search(unit_vector(1), owner_id=owner_a, top_k=10, document_ids=[str(doc_1)])

    # doc_2's chunk is the closer match, but it's excluded by document_ids,
    # and doc_1 (an exact non-match) is correctly returned as the
    # only candidate left in scope - not silently dropped.
    assert len(results) == 1
    assert results[0]["document_id"] == str(doc_1)


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_legacy_chunks_without_owner_id_are_never_returned(owner_a):
    """
    Regression test for the exact bug found after Option A / re-indexing:
    chunks written before the owner_id fix have no owner_id in their
    metadata and must stay excluded by default (deny, not allow) rather
    than being treated as unowned/public.
    """
    store = FaissStore()
    legacy_doc = uuid4()
    store.add(legacy_doc, ["a chunk"], [unit_vector(0)], owner_id=owner_a)

    # Simulate a pre-fix chunk by stripping owner_id back out of the
    # metadata that was just written, the way old data would look.
    for entry in store._metadata.values():
        entry.pop("owner_id", None)

    results = store.search(unit_vector(0), owner_id=owner_a, top_k=10)

    assert results == []


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_search_sees_documents_added_by_a_separate_store_instance(owner_a):
    """
    Regression test for a real production bug: ai-worker-service's API
    (search) and its Celery worker (indexing) run as SEPARATE processes
    (see docker-compose.yml) sharing the same on-disk vector_store volume,
    each with its own FaissStore instance/memory. Without reloading on a
    detected on-disk change, a document indexed by the worker was
    permanently invisible to the API's search - the API process loaded the
    index once and never looked at the disk again, so a user who uploaded
    a document right after asking an empty-state question ("I don't know")
    would get that exact same "I don't know" forever, no matter how many
    documents they uploaded afterward.
    """
    doc = uuid4()

    # This store simulates the long-lived FastAPI search process - created
    # once and reused, just like get_store()'s module-level singleton.
    api_process_store = FaissStore()
    assert api_process_store.search(unit_vector(0), owner_id=owner_a, top_k=5) == []

    # This simulates the SEPARATE Celery worker process/container - same
    # on-disk directory, but a genuinely different Python object with no
    # shared memory, the way two containers actually are.
    import time
    time.sleep(0.01)  # guarantee a distinct file mtime from the initial load
    worker_process_store = FaissStore()
    worker_process_store.add(doc, ["a newly uploaded chunk"], [unit_vector(0)], owner_id=owner_a)

    # The ORIGINAL api_process_store object - not a fresh one - must now
    # see the new document on its very next search call.
    results = api_process_store.search(unit_vector(0), owner_id=owner_a, top_k=5)
    assert len(results) == 1
    assert results[0]["document_id"] == str(doc)


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_add_requires_an_owner_id():
    store = FaissStore()
    with pytest.raises(ValueError):
        store.add(uuid4(), ["text"], [unit_vector(0)], owner_id="")


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_search_requires_an_owner_id():
    store = FaissStore()
    with pytest.raises(ValueError):
        store.search(unit_vector(0), owner_id="", top_k=5)


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_search_on_empty_index_returns_no_results(owner_a):
    store = FaissStore()
    assert store.search(unit_vector(0), owner_id=owner_a, top_k=5) == []


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_data_survives_a_reload_from_disk(owner_a):
    doc = uuid4()
    first_store = FaissStore()
    first_store.add(doc, ["persisted chunk"], [unit_vector(0)], owner_id=owner_a)

    reloaded_store = FaissStore()  # simulates a fresh process picking the index back up
    results = reloaded_store.search(unit_vector(0), owner_id=owner_a, top_k=5)

    assert len(results) == 1
    assert results[0]["text"] == "persisted chunk"


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_delete_document_removes_it_from_search_and_returns_chunk_count(owner_a):
    store = FaissStore()
    doc = uuid4()
    store.add(doc, ["chunk one", "chunk two"], [unit_vector(0), unit_vector(1)], owner_id=owner_a)

    deleted_count = store.delete_document(doc, owner_id=owner_a)

    assert deleted_count == 2
    assert store.search(unit_vector(0), owner_id=owner_a, top_k=5) == []
    assert store.search(unit_vector(1), owner_id=owner_a, top_k=5) == []


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_delete_document_leaves_other_documents_fully_intact(owner_a):
    store = FaissStore()
    doc_1, doc_2 = uuid4(), uuid4()
    store.add(doc_1, ["doc 1 chunk"], [unit_vector(0)], owner_id=owner_a)
    store.add(doc_2, ["doc 2 chunk"], [unit_vector(1)], owner_id=owner_a)

    store.delete_document(doc_1, owner_id=owner_a)

    results = store.search(unit_vector(1), owner_id=owner_a, top_k=5)
    assert len(results) == 1
    assert results[0]["document_id"] == str(doc_2)


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_delete_document_does_not_remove_another_owners_document_with_the_same_id_coincidence(owner_a, owner_b):
    """
    Defense in depth: even though document-service already checks
    ownership before ever calling this, delete_document() must not trust
    document_id alone - it independently re-checks owner_id, the same way
    search() does, rather than assuming the caller already got it right.
    """
    store = FaissStore()
    doc = uuid4()
    store.add(doc, ["owner a's chunk"], [unit_vector(0)], owner_id=owner_a)

    deleted_count = store.delete_document(doc, owner_id=owner_b)

    assert deleted_count == 0
    # owner_a's chunk must still be fully intact and searchable.
    results = store.search(unit_vector(0), owner_id=owner_a, top_k=5)
    assert len(results) == 1


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_delete_document_on_a_document_with_no_indexed_chunks_is_a_safe_noop(owner_a):
    store = FaissStore()
    result = store.delete_document(uuid4(), owner_id=owner_a)
    assert result == 0


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_delete_requires_an_owner_id():
    store = FaissStore()
    with pytest.raises(ValueError):
        store.delete_document(uuid4(), owner_id="")


@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_delete_document_is_visible_across_separate_store_instances(owner_a):
    """
    Same cross-process concern as the staleness regression test above:
    document-service (which triggers the delete) and the process serving
    /internal/search are separate containers. A deletion made through one
    FaissStore instance must be visible to a different, already-loaded
    instance on its next call.
    """
    doc = uuid4()
    writer_store = FaissStore()
    writer_store.add(doc, ["a chunk"], [unit_vector(0)], owner_id=owner_a)

    reader_store = FaissStore()
    assert len(reader_store.search(unit_vector(0), owner_id=owner_a, top_k=5)) == 1

    import time
    time.sleep(0.01)
    writer_store.delete_document(doc, owner_id=owner_a)

    # The reader's ORIGINAL object, not a fresh one.
    assert reader_store.search(unit_vector(0), owner_id=owner_a, top_k=5) == []
