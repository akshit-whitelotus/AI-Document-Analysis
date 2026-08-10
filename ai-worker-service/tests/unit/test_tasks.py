import json
from unittest.mock import MagicMock,patch
from uuid import uuid4
import pytest
import app.tasks as tasks
from app.models.document import DocumentStatus

def make_fake_document(owner_id: str):
    doc=MagicMock()
    doc.owner_id=owner_id
    doc.status = None
    doc.chunk_count=None
    doc.error_message=None
    return doc

@pytest.fixture
def fake_session(monkeypatch):
    document=make_fake_document(owner_id=str(uuid4()))
    session=MagicMock()
    session.get.return_value=document
    monkeypatch.setattr(tasks, "SessionLocal", lambda:session)
    return session,document

@pytest.fixture
def chunks_sidecar(tmp_path,monkeypatch):
    monkeypatch.setattr(tasks, "UPLOAD_DIR",tmp_path)

    def _write(document_id:str, chunks:list[str]):
        (tmp_path / f"{document_id}.chunks.json").write_text(json.dumps({"chunks":chunks}))
    return _write

@pytest.fixture
def mocked_pipeline():
    with patch.object(tasks,"embed_texts") as embed_texts, \
         patch.object(tasks,"get_store") as get_store, \
         patch.object(tasks,"celery_app") as celery_app, \
         patch.object(tasks,"publish_document_status") as publish_document_status:
        embed_texts.return_value = [[0.0] * 384]
        yield {"embed_texts":embed_texts,"get_store":get_store,"celery_app":celery_app,"publish_document_status":publish_document_status}

def test_process_document_happy_path_indexes_with_owner_id(fake_session, chunks_sidecar, mocked_pipeline):
    session, document = fake_session
    document_id = str(uuid4())
    chunks_sidecar(document_id, ["chunk one"])

    tasks.process_document.run(document_id)

    assert document.status == DocumentStatus.PROCESSED.value
    assert document.chunk_count == 1
    # This is the actual regression check for the owner_id fix: the
    # document's owner must be passed into the vector store at index time,
    # or search() will never be able to find these chunks for anyone.
    mocked_pipeline["get_store"].return_value.add.assert_called_once_with(
        document_id, ["chunk one"], mocked_pipeline["embed_texts"].return_value, owner_id=str(document.owner_id)
    )
    mocked_pipeline["celery_app"].send_task.assert_called_once()
    mocked_pipeline["publish_document_status"].assert_called_once_with(
        str(document.owner_id),
        {"document_id": document_id, "status": DocumentStatus.PROCESSED.value, "chunk_count": 1},
    )

def test_process_document_sets_processing_status_before_indexing(fake_session,chunks_sidecar,mocked_pipeline):
    session,document = fake_session
    document_id = str(uuid4())
    chunks_sidecar(document_id, ["chunk one"])
    statuses_seen = []
    mocked_pipeline["get_store"].return_value.add.side_effect = lambda *a, **k: statuses_seen.append(document.status)

    tasks.process_document.run(document_id)
    assert statuses_seen == [DocumentStatus.PROCESSING.value]

def test_process_document_missing_sidecar_file_marks_document_failed(fake_session,chunks_sidecar,mocked_pipeline):
    session,document = fake_session
    document_id = str(uuid4())
    # deliberately not calling chunks_sidecar(...) - no file written
    
    with pytest.raises(FileNotFoundError):
        tasks.process_document.run(document_id)
    assert document.status == DocumentStatus.FAILED.value
    assert "Missing chunk sidecar file" in document.error_message
    mocked_pipeline["get_store"].return_value.add.assert_not_called()

def test_process_document_embedding_failure_marks_document_failed(fake_session,chunks_sidecar,mocked_pipeline):
    session,document = fake_session
    document_id = str(uuid4())
    chunks_sidecar(document_id,["chunk one"])
    mocked_pipeline["embed_texts"].side_effect = RuntimeError("embedding backend unreachable")
    
    with pytest.raises(RuntimeError):
        tasks.process_document.run(document_id)
    assert document.status == DocumentStatus.FAILED.value
    assert "embedding backend unreachable" in document.error_message
    mocked_pipeline["publish_document_status"].assert_called_once_with(
        str(document.owner_id),
        {
            "document_id": document_id,
            "status": DocumentStatus.FAILED.value,
            "error_message": "embedding backend unreachable",
        },
    )

def test_process_document_missing_sidecar_failure_also_publishes_a_failed_status(fake_session,chunks_sidecar,mocked_pipeline):
    session,document = fake_session
    document_id = str(uuid4())
    # deliberately not calling chunks_sidecar(...) - no file written

    with pytest.raises(FileNotFoundError):
        tasks.process_document.run(document_id)

    mocked_pipeline["publish_document_status"].assert_called_once()
    published_owner_id, published_payload = mocked_pipeline["publish_document_status"].call_args.args
    assert published_owner_id == str(document.owner_id)
    assert published_payload["status"] == DocumentStatus.FAILED.value

def test_process_document_missing_document_row_is_a_noop(fake_session,mocked_pipeline):
    session, _ =fake_session
    session.get.return_value=None

    tasks.process_document.run(str(uuid4()))

    mocked_pipeline["get_store"].return_value.add.assert_not_called()
    mocked_pipeline["celery_app"].send_task.assert_not_called()
    mocked_pipeline["publish_document_status"].assert_not_called()
