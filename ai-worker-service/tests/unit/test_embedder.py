from unittest.mock import patch
from app.embeddings import embedder

def test_embed_texts_of_empty_list_skips_loading_the_model():
    with patch.object(embedder,"get_model") as get_model:
        result = embedder.embed_texts([])
    assert result == []
    get_model.assert_not_called()

def test_embed_texts_returns_one_vector_per_input_text():
    vectors = embedder.embed_texts(["first chunk","second chunk"])

    assert len(vectors) == 2
    assert len(vectors[0]) == 384

def test_embed_query_returns_a_single_vector_not_a_list_of_vectors():
    vector=embedder.embed_query("a question")

    assert isinstance(vector[0], float)
    assert len(vector) == 384
    