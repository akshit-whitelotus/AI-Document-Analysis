from uuid import uuid4
import numpy as np
import pytest
from app.vectorstore.faiss_store import FaissStore,EMBEDDING_DIM

def unit_vector(hot_index: int) -> list[float]:
    """A simple one-hot unit vector, so inner-product search gives an
    unambigous, deterministic ranking between vectors."""
    v=np.zeros(EMBEDDING_DIM,dtype="float32")
    v[hot_index] = 1.0
    return v.tolist()

@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_search_never_returns_another_owners_chunks(owner_a,owner_b):
    store=FaissStore()
    doc_a,doc_b = uuid4(),uuid4()
    store.add(doc_a,["owner A's private text"],[unit_vector(0)],owner_id=owner_a)
    store.add(doc_b,["owner B's private text"],[unit_vector(0)],owner_id=owner_b)

    # Both documents have the *identical* vector, so without owner
    # filtering this query would return both - the whole point of the fix.
    results= store.search(unit_vector(0),owner_id=owner_a,top_k=10)

    assert len(results) == 1
    assert results[0]["document_id"] == str(doc_a)
    assert all(r["document_id"] != str(doc_b) for r in results)

@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_document_ids_filter_still_applies_within_one_owner(owner_a):
    store=FaissStore()
    doc_1,doc_2 = uuid4(),uuid4()
    store.add(doc_1,["chunk in doc 1"],[unit_vector(0)],owner_id=owner_a)
    store.add(doc_2,["chunk in doc 2"],[unit_vector(1)],owner_id=owner_a)

    results=store.search(unit_vector(1),owner_id=owner_a,top_k=10,document_ids=[str(doc_1)])


    # doc_2's chunk is the closer match, but it's excluded by document_ids,
    # and doc_1 (an exact non-match) is correctly returned as the 
    # only candidate left in scope - not silently dropped.
    assert len(results) == 1
    assert results[0]["document_id"] == str(doc_1)

@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_legacy_chunks_without_owner_id_are_never_returned(owner_a):
    """
    Regression test for the exact bug found after Option A / re-indexing:
    chunks written before the owner_if fix have no owner_id in their
    metadata and must stay excluded by default (deny, not allow) rather
    than being treated as unowned/public.
    """
    store=FaissStore()
    legacy_doc=uuid4()
    store.add(legacy_doc,["a chunk"],[unit_vector(0)],owner_id=owner_a)

    # Simulate a pre-fix chunk by stripping owner_if back out of the 
    # metadata that was just written, the way old data would look.
    for entry in store._metadata.values():
        entry.pop("owner_id",None)
    results = store.search(unit_vector(0), owner_id=owner_a , top_k=10)
    assert results == []

@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_add_requires_an_owner_id():
    store = FaissStore()
    with pytest.raises(ValueError):
        store.add(uuid4(),["text"],[unit_vector(0)],owner_id="")

@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_search_requires_an_owner_id():
    store=FaissStore()
    with pytest.raises(ValueError):
        store.search(unit_vector(0),owner_id="",top_k=5)

@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_search_on_empty_index_returns_no_results(owner_a):
    store=FaissStore()
    assert store.search(unit_vector(0),owner_id=owner_a,top_k=5) == []

@pytest.mark.usefixtures("isolated_vector_store_dir")
def test_data_survives_a_reload_from_disk(owner_a):
    doc=uuid4()
    first_store=FaissStore()
    first_store.add(doc,["persisted chunk"],[unit_vector(0)],owner_id=owner_a)

    reloaded_store=FaissStore()
    results= reloaded_store.search(unit_vector(0),owner_id=owner_a,top_k=5)

    assert len(results) == 1
    assert results[0]["text"] == "persisted chunk"