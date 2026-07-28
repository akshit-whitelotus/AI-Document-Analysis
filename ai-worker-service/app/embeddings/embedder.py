from functools import lru_cache
from sentence_transformers import SentenceTransformer

from shared.config.settings import settings

@lru_cache
def get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.EMBEDDING_MODEL)

def embed_texts(texts:list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = get_model()
    vectors=model.encode(texts,normalize_embeddings=True,convert_to_numpy=True)
    return vectors.tolist()

def embed_query(text:str) -> list[float]:
    return embed_texts([text])[0]
