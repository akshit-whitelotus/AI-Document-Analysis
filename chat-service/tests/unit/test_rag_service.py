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
    session_id,history = service._sessions.set.call_args.args[:2]
    assert session_id == "session-1"
    assert history[-1] == {"question":"A question","answer":"This is the answer."}
