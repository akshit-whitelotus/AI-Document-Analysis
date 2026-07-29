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
    def add(self,document_id:UUID,chunks:list[str],vectors:list[list[float]]) -> int:
        with _lock:
            if not chunks:
                return 0
            ids=np.arange(self._next_id,self._next_id+len(chunks),dtype=np.int64)
            matrix=np.array(vectors,dtype=np.float32)
            self.index.add_with_ids(matrix,ids)

            for offset , (chunk_id,text) in enumerate(zip(ids,chunks)):
                self._metadata[int(chunk_id)] = {
                    "document_id":str(document_id),
                    "chunk_index":offset,
                    "text":text
                }
            self._next_id +=len(chunks)
            self._save()
            return len(chunks)
    def search(self,query_vector:list[float],top_k: int=5) -> list[dict]:
        with _lock:
            if self.index.ntotal == 0:
                return []
            query=np.array([query_vector],dtype=np.float32)
            scores,ids=self.index.search(query,min(top_k,self.index.ntotal))

            results=[]
            for score,chunk_id in zip(scores[0],ids[0]):
                if chunk_id == -1 :
                    continue
                meta=self._metadata.get(int(chunk_id))
                if meta:
                    results.append({**meta, "score":float(score)})
            return results

_store:FaissStore | None=None

def get_store() -> FaissStore:
    global _store
    if _store is None:
        _store=FaissStore()
    return _store
