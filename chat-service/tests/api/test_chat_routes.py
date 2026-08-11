from unittest.mock import AsyncMock,MagicMock
from uuid import uuid4
import pytest
from httpx import AsyncClient,ASGITransport
from app.main import app
from app.schemas.chat_query import ChatQueryResponse,SourceChunk
from shared.security.oauth import get_current_user,CurrentUser

async def _fake_event_stream(events:list[dict]):
    for event in events:
        yield event

DEFAULT_STREAM_EVENTS=[
    {"type":"sources","sources":[]},
    {"type":"delta","text":"This "},
    {"type":"delta","text":"is the answer."},
    {"type":"done","cached":False},
]

@pytest.fixture
def mock_rag_service():
    service=MagicMock()
    service.answer=AsyncMock(
        return_value=ChatQueryResponse(
            answer="This is the answer.",
            sources=[
                SourceChunk(document_id=str(uuid4()),chunk_index=0,text="some context",score=0.9)
            ],
            cached=False,
        )
    )
    service.answer_stream=MagicMock(return_value=_fake_event_stream(DEFAULT_STREAM_EVENTS))
    return service

@pytest.fixture
def client(mock_rag_service):
    app.state.rag_service=mock_rag_service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=uuid4(),raw_claims={})

    yield AsyncClient(transport=ASGITransport(app=app),base_url="http://test")
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_query_returns_answer_and_scores(client,mock_rag_service):
    async with client as ac:
        response = await ac.post(
            "/api/v1/chat/query",
            json={"session_id":"s1","question":"What changed?","top_k":5,"document_ids":None}

        )
    assert response.status_code == 200
    body=response.json()
    assert body["answer"] == "This is the answer."
    assert len(body["sources"]) == 1

@pytest.mark.asyncio
async def test_query_passes_the_authenticated_users_id_as_owner_id(client,mock_rag_service):
    async with client as ac :
        await ac.post(
            "/api/v1/chat/query",
            json={"session_id":"s1","question":"What changed","top_k":5 , "documents_ids":None},
        )
    mock_rag_service.answer.assert_awaited_once()
    call_kwargs=mock_rag_service.answer.await_args.kwargs
    call_args=mock_rag_service.answer.await_args.args

    passed_owner_id=call_kwargs.get("owner_id") or (call_args[3] if len(call_args) > 3 else None)
    assert passed_owner_id is not None,(
        "rag_service_answer() was called without an owner_id - the"
        "chat_query_route.py -> rag_service_answer() wiring for the"
        "owner_id fix is missing or broken"
    )

@pytest.mark.asyncio
async def test_query_without_token_returns_401():
    app.dependency_overrides.clear()
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac :
        response = await ac.post(
            "/api/v1/chat/query",
            json={"session_id":"s1","question":"hi","top_k":5}
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_query_stream_returns_sse_content_type_and_full_event_sequence(client):
    import json as jsonlib

    async with client as ac:
        response = await ac.post(
            "/api/v1/chat/query/stream",
            json={"session_id": "s1", "question": "What changed?", "top_k": 5, "document_ids": None},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(jsonlib.loads(line[len("data: "):]))

    assert events == DEFAULT_STREAM_EVENTS


@pytest.mark.asyncio
async def test_query_stream_passes_the_authenticated_users_id_as_owner_id(client, mock_rag_service):
    async with client as ac:
        await ac.post(
            "/api/v1/chat/query/stream",
            json={"session_id": "s1", "question": "What changed?", "top_k": 5, "document_ids": None},
        )

    mock_rag_service.answer_stream.assert_called_once()
    call_kwargs = mock_rag_service.answer_stream.call_args.kwargs
    call_args = mock_rag_service.answer_stream.call_args.args
    passed_owner_id = call_kwargs.get("owner_id") or (call_args[3] if len(call_args) > 3 else None)
    assert passed_owner_id is not None


@pytest.mark.asyncio
async def test_query_stream_without_token_returns_401():
    app.dependency_overrides.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/chat/query/stream",
            json={"session_id": "s1", "question": "hi", "top_k": 5},
        )
    assert response.status_code == 401
    
