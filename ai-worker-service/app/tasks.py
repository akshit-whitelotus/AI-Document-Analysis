import json
from pathlib import Path
from uuid import UUID

from shared.config.settings import settings
from shared.logger.logger import get_logger
from shared.messaging.celery_app import celery_app
from shared.schemas.events import TOPIC_DOCUMENT_PROCESSED,TOPIC_DOCUMENT_UPLOADED

from app.db.session import SessionLocal
from app.embeddings.embedder import embed_texts
from app.models.document import DocumentStatus,Document
from app.vectorstore.faiss_store import get_store

logger=get_logger(__name__)

UPLOAD_DIR=Path(settings.UPLOAD_DIR)

@celery_app.task(name=TOPIC_DOCUMENT_UPLOADED,bind=True,max_retries=3,default_retry_delay=10)
def process_document(self, document_id: str) -> None:
    session=SessionLocal()
    try:
        document=session.get(Document,UUID(document_id))
        if document is None :
            logger.warning("process_document: document not found",document_id=document_id)
            return
        document.status=DocumentStatus.PROCESSING.value
        session.commit()

        chunks_path=UPLOAD_DIR / f"{document_id}.chunks.json"
        if not chunks_path.exists():
            raise FileNotFoundError(f"Missing chunk sidecar file: {chunks_path}")
        chunks=json.loads(chunks_path.read_text())["chunks"]
        vectors=embed_texts(chunks)
        get_store().add(document_id,chunks,vectors,owner_id=str(document.owner_id))

        document.status=DocumentStatus.PROCESSED.value
        document.chunk_count=len(chunks)
        session.commit()

        celery_app.send_task(TOPIC_DOCUMENT_PROCESSED,args=[document_id])
        logger.info("process_document:completed",document_id=document_id,chunks=len(chunks))
    except Exception as exc:
        session.rollback()
        document=session.get(Document,UUID(document_id))
        if document is not None:
            document.status=DocumentStatus.FAILED.value
            document.error_message=str(exc)
            session.commit()
        logger.error("process_document: failed",document_id=document_id,error=str(exc))
        raise self.retry(exc=exc)
    finally:
        session.close()

@celery_app.task(name=TOPIC_DOCUMENT_PROCESSED)
def notify_document_processed(document_id:str) -> None:
    logger.info("Cleanup_expired_sessions: ran (Redis TTLs handle actual expiry)")

@celery_app.task(name="cleanup_expired_sessions")
def cleanup_expired_sessions() -> None:
    logger.info("cleanup_expired_sessions : ran (Redis TTLs handle actual expiry)")

@celery_app.task(name="reindex_pending_documents")
def reindex_pending_documents() -> None:
    session=SessionLocal()
    try:
        stuck = (
            session.query(Document)
            .filter(Document.status.in_([DocumentStatus.PENDING.value,DocumentStatus.PROCESSING.value]))
            .all()
        )
        for document in stuck:
            logger.info("reindex_pending_documents: re-queueing",document_id=str(document.id))
            celery_app.send_task(TOPIC_DOCUMENT_UPLOADED,args=[str(document.id)])
    finally:
        session.close()
        
