import pytest
from tests.conftest import make_search_response

SAMPLE_CHUNK = {
    "document_id":"11111111-1111-1111-1111-11111111",
    "chunk_index":0,
    "text":"Revenue grew 12% year over year. ",
    "score":0.87
}

@pytest.mark.asyncio
async def test_answer_owner_id_to_the_worker(rag_service_with_mocked_dependencies):
    service = rag_service_with_mocked_dependencies
    service._worker_client.post.return_value = make_search_response([SAMPLE_CHUNK])

    await service.answer("session-1","How much did revenue grow?",top_k=5,owner_id="user-abc")
    service._worker_client.post.assert_awaited_once()
    _,kwargs = service._worker_client.post.call_args
    assert kwargs["json"]["owner_id"] == "user-abc"

@pytest.mark.asyncio
async def test_answer_never_lets_a_missing_owner_id_reach_the_worker(rag_service_with_mocked_dependencies):
    service = rag_service_with_mocked_dependencies
    service._worker_client.post.return_value = make_search_response([])
    with pytest.raises(TypeError):
        await service.answer("session-1","question",top_k=5)

@pytest.mark.asyncio
async def test_answer_returns_llm_response_and_sources(rag_service_with_mocked_dependencies):
    service =rag_service_with_mocked_dependencies
    service._worker_client.post.return_value = make_search_response([SAMPLE_CHUNK])
    result = await service.answer("session-1","How much did revenue grow?",top_k=5,owner_id="user-abc")

    assert result.answer == "This is the answer."
    assert result.cached is False
    assert len(result.sources) == 1
    assert result.sources[0].document_id == SAMPLE_CHUNK["document_id"]
    service._llm_client.generate.assert_awaited_once()

@pytest.mark.asyncio
async def test_answer_uses_cache_when_available_and_skips_the_llm(rag_service_with_mocked_dependencies):
    service = rag_service_with_mocked_dependencies
    service._worker_client.post.return_value=make_search_response([SAMPLE_CHUNK])
    service._cache.get.return_value="A cached answer."
    result = await service.answer("session-1" , "How much did revenue grow?" , top_k=5,owner_id="user-abc")

    assert result.answer == "A cached answer."
    assert result.cached is True
    service._llm_client.generate.assert_not_awaited()

@pytest.mark.asyncio
async def test_different_owners_get_different_cache_keys_for_the_same_question(rag_service_with_mocked_dependencies):
    service = rag_service_with_mocked_dependencies
    service._worker_client.post.return_value = make_search_response([SAMPLE_CHUNK])

    await service.answer("session-1" , "How much did revenue grow?", top_k=5 , owner_id="user-a")
    await service.answer("session-2" , "How much did revenue grow?", top_k=5 , owner_id="user-b")

    first_cache_key = service._cache.set.call_args_list[0].args[0]
    second_cache_key = service._cache.set.call_args_list[1].args[0]
    assert first_cache_key != second_cache_key

@pytest.mark.asyncio
async def test_answer_appends_to_session_history(rag_service_with_mocked_dependencies):
    service = rag_service_with_mocked_dependencies
    service._worker_client.post.return_value = make_search_response([])

    await service.answer("session-1","A question",top_k=5,owner_id = "user-abc")

    service._sessions.set.assert_awaited_once()
    key,history = service._sessions.set.call_args.args[:2]
    assert key == "user-abc:session-1"
    assert history[-1] == {"question":"A question","answer":"This is the answer."}


@pytest.mark.asyncio
async def test_answer_stream_yields_sources_then_deltas_then_done(rag_service_with_mocked_dependencies):
    service = rag_service_with_mocked_dependencies
    service._worker_client.post.return_value = make_search_response([SAMPLE_CHUNK])

    events = [e async for e in service.answer_stream("session-1", "A question", top_k=5, owner_id="user-abc")]

    assert events[0]["type"] == "sources"
    assert events[0]["sources"][0]["document_id"] == SAMPLE_CHUNK["document_id"]
    assert [e["type"] for e in events[1:-1]] == ["delta", "delta", "delta"]
    assert "".join(e["text"] for e in events[1:-1]) == "This is the answer."
    assert events[-1] == {"type": "done", "cached": False}


@pytest.mark.asyncio
async def test_answer_stream_caches_the_assembled_full_answer(rag_service_with_mocked_dependencies):
    service = rag_service_with_mocked_dependencies
    service._worker_client.post.return_value = make_search_response([])

    [e async for e in service.answer_stream("session-1", "A question", top_k=5, owner_id="user-abc")]

    service._cache.set.assert_awaited_once()
    cached_value = service._cache.set.call_args.args[1]
    assert cached_value == "This is the answer."


@pytest.mark.asyncio
async def test_answer_stream_uses_cache_and_skips_the_llm_entirely(rag_service_with_mocked_dependencies):
    service = rag_service_with_mocked_dependencies
    service._worker_client.post.return_value = make_search_response([])
    service._cache.get.return_value = "A cached answer."

    events = [e async for e in service.answer_stream("session-1", "A question", top_k=5, owner_id="user-abc")]

    assert events[0]["type"] == "sources"
    assert events[1] == {"type": "delta", "text": "A cached answer."}
    assert events[2] == {"type": "done", "cached": True}
    service._llm_client.generate_stream.assert_not_called()


@pytest.mark.asyncio
async def test_answer_stream_appends_the_full_assembled_answer_to_session_history(rag_service_with_mocked_dependencies):
    service = rag_service_with_mocked_dependencies
    service._worker_client.post.return_value = make_search_response([])

    [e async for e in service.answer_stream("session-1", "A question", top_k=5, owner_id="user-abc")]

    service._sessions.set.assert_awaited_once()
    _, history = service._sessions.set.call_args.args[:2]
    assert history[-1] == {"question": "A question", "answer": "This is the answer."}


class _InMemorySessions:
    """A real (if tiny) key-value store, standing in for SessionStore, so
    these two tests can prove actual cross-key isolation rather than just
    asserting on a mock's call args."""
    def __init__(self):
        self._data = {}
    async def get(self, key):
        return self._data.get(key)
    async def set(self, key, value, ttl_seconds=None):
        self._data[key] = value


@pytest.mark.asyncio
async def test_two_users_with_the_same_session_id_get_independent_document_scopes(rag_service_with_mocked_dependencies):
    """
    Regression test: session_id is client-generated and not a secret (see
    frontend/index.html - it's stored in localStorage), so two different
    users could easily end up presenting the identical session_id string.
    Their document scopes must never collide.
    """
    service = rag_service_with_mocked_dependencies
    service._sessions = _InMemorySessions()

    await service.set_session_documents("user-a", "shared-session-id", ["doc-a"])
    await service.set_session_documents("user-b", "shared-session-id", ["doc-b"])

    assert await service.get_session_documents("user-a", "shared-session-id") == ["doc-a"]
    assert await service.get_session_documents("user-b", "shared-session-id") == ["doc-b"]


@pytest.mark.asyncio
async def test_two_users_with_the_same_session_id_get_independent_history(rag_service_with_mocked_dependencies):
    service = rag_service_with_mocked_dependencies
    service._sessions = _InMemorySessions()
    service._worker_client.post.return_value = make_search_response([])

    await service.answer("shared-session-id", "Alice's question", top_k=5, owner_id="user-a")
    await service.answer("shared-session-id", "Bob's question", top_k=5, owner_id="user-b")

    alice_history = await service._sessions.get(service._history_key("user-a", "shared-session-id"))
    bob_history = await service._sessions.get(service._history_key("user-b", "shared-session-id"))
    assert [h["question"] for h in alice_history] == ["Alice's question"]
    assert [h["question"] for h in bob_history] == ["Bob's question"]
