import json,threading
from pathlib import Path
from uuid import UUID
import faiss
import numpy as np
from shared.config.settings import settings

STORE_DIR=Path(settings.VECTOR_STORE_DIR)
INDEX_PATH=STORE_DIR/"index.faiss"
METADATA_PATH=STORE_DIR/"metadata.json"
EMBEDDING_DIM=384

_lock=threading.Lock()

class FaissStore:
    def __init__(self):
        STORE_DIR.mkdir(parents=True,exist_ok=True)
        self._next_id=0
        self._metadata:dict[int,dict]={}
        self.index=self._load_or_create_index()
        self._load_metadata()
    def _load_or_create_index(self) -> faiss.Index:
        if INDEX_PATH.exists():
            return faiss.read_index(str(INDEX_PATH))
        base=faiss.IndexFlatIP(EMBEDDING_DIM)
        return faiss.IndexIDMap(base)
    def _load_metadata(self) -> None:
        if METADATA_PATH.exists():
            raw = json.loads(METADATA_PATH.read_text())
            self._metadata={int(k):v for k,v in raw["metadata"].items()}
            self._next_id=raw["next_id"]
    def _save(self) -> None:
        faiss.write_index(self.index,str(INDEX_PATH))
        METADATA_PATH.write_text(json.dumps({"metadata":self._metadata,"next_id":self._next_id}))

    def add(self,document_id:UUID,chunks:list[str],vectors:list[list[float]],owner_id:str) -> int:
        """owner_id is REQUIRED - every indexed chunk must be tagged with the
        document's owner so search() can enforce per-user isolation. Chunks
        indexed without an owner_id can never be matched by search() (see
        below), so a missing owner_id here would just make the document
        invisible to everyone rather than leaking it - fail loudly instead."""
        if not owner_id:
            raise ValueError("owner_id is required when indexing a document")
        with _lock:
            if not chunks:
                return 0
            ids=np.arange(self._next_id,self._next_id+len(chunks),dtype=np.int64)
            matrix=np.array(vectors,dtype=np.float32)
            self.index.add_with_ids(matrix,ids)

            for offset , (chunk_id,text) in enumerate(zip(ids,chunks)):
                self._metadata[int(chunk_id)] = {
                    "document_id":str(document_id),
                    "owner_id":str(owner_id),
                    "chunk_index":offset,
                    "text":text
                }
            self._next_id +=len(chunks)
            self._save()
            return len(chunks)

    def search(self,query_vector:list[float],owner_id:str,top_k: int=5,document_ids:list[str] | None=None) -> list[dict]:
        """owner_id is REQUIRED and always enforced - a caller can never widen
        a search beyond their own documents, regardless of what (if anything)
        is passed in document_ids. Legacy chunks indexed before owner_id
        existed have no owner_id in their metadata and are excluded by
        default (deny, not allow) rather than being treated as unowned/public."""
        if not owner_id:
            raise ValueError("owner_id is required for search")
        with _lock:
            if self.index.ntotal == 0:
                return []
            query=np.array([query_vector],dtype=np.float32)

            # FAISS's flat index has no built-in metadata filter, so we search
            # the full index and filter + truncate ourselves. IndexFlatIP is
            # an EXACT (not approximate) index, so over-fetching candidates
            # doesn't lose recall - it's just a wider scan before we keep the
            # top_k matching ones.
            search_k = self.index.ntotal
            scores,ids=self.index.search(query,search_k)

            wanted_docs = set(document_ids) if document_ids else None
            results=[]
            for score,chunk_id in zip(scores[0],ids[0]):
                if chunk_id == -1 :
                    continue
                meta=self._metadata.get(int(chunk_id))
                if not meta:
                    continue
                # Hard ownership check - never optional, never skipped.
                if meta.get("owner_id") != str(owner_id):
                    continue
                if wanted_docs is not None and meta["document_id"] not in wanted_docs:
                    continue
                results.append({**meta, "score":float(score)})
                if len(results) >= top_k:
                    break
            return results

_store:FaissStore | None=None

def get_store() -> FaissStore:
    global _store
    if _store is None:
        _store=FaissStore()
    return _store