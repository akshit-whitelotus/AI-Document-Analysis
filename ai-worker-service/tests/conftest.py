"""
sentence_transformers pulls in torch and downloads a real model on first
use - far too heavy/slow for a test suite, and the actual embedding math
isn't what these tests are about. This stub is installed into
sys.modules *before* anything imports app.embeddings.embedder (which does
`from sentence_transformers import SentenceTransformer` at module level),
so every test in this service gets a fast, deterministic fake instead.

This has to happen at collection time, before any `app.*` import, which is
why it's here at the top of conftest.py rather than inside a fixture.
"""
import sys
import types

if "sentence_transformers" not in sys.modules:
    _fake_module = types.ModuleType("sentence_transformers")

    class _FakeSentenceTransformer:
        def __init__(self,*args,**kwargs):
            pass
        def encode(self,texts, normalize_embeddings = True , convert_to_numpy = True):
            import numpy as np
            # Deterministic, cheap, and correctly shaped (384-dim to match
            # EMBEDDING_DIM in faiss_store.py) - good enough for tests that
            # care about *whether* embedding happened, not the actual vectors.
            return np.zeros((len(texts),384),dtype="float32")
    _fake_module.SentenceTransformer = _FakeSentenceTransformer
    sys.modules["sentence_transformers"] = _fake_module

import pytest
from uuid import uuid4

@pytest.fixture
def owner_a():
    return str(uuid4())

@pytest.fixture
def owner_b():
    return str(uuid4())

@pytest.fixture
def isolated_vector_store_dir(tmp_path,monkeypatch):
    """
    Points FaissStore at a throwaway directory and clears the module-level
    get_store() singleton cache, so each test starts with a fresh, empty
    index instead of sharing state (or writing into the real vector_store/).
    """
    import app.vectorstore.faiss_store as faiss_store_module

    monkeypatch.setattr(faiss_store_module,"STORE_DIR",tmp_path)
    monkeypatch.setattr(faiss_store_module,"INDEX_PATH",tmp_path / "index.faiss")
    monkeypatch.setattr(faiss_store_module,"METADATA_PATH",tmp_path / "metadata.json")
    monkeypatch.setattr(faiss_store_module,"_store",None)
    return tmp_path
