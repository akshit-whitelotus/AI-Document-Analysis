import json
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from shared.cache.redis_client import publish_document_status
from shared.config.settings import settings
from shared.logger.logger import get_logger
from shared.messaging.celery_app import celery_app
from shared.schemas.events import TOPIC_DOCUMENT_PROCESSED,TOPIC_DOCUMENT_UPLOADED
from shared.utils.datetime import utc_now

from app.db.session import SessionLocal
from app.embeddings.embedder import embed_texts
from app.models.document import DocumentStatus,Document
from app.vectorstore.faiss_store import get_store

logger=get_logger(__name__)

UPLOAD_DIR=Path(settings.UPLOAD_DIR)

# How long a document can sit in PENDING/PROCESSING before reindex_pending_docments
# (below) is willing to consider it "stuck" and re-queue it. Must comfortably
# exceed how long a single document can legitimately take to process(embedding
# a large PDF, cold model load, etc.) - otherwise the beat schedule below
# (every 10 minutes) will re-queue documents that are still actively being
# worked on, causing the same document to be emebedded twice and producing
# duplicate chunks in the FAISS index (get_store().add() only ever appends;
# it has no notion of "I've already indexed this document_id").
REINDEX_STALE_AFTER=timedelta(minutes=20)

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

        # Idempotency guard: this task can run more than once for the same 
        # document_id - a celery redelivery after a worker crash (acks_late=True
        # means the broker resend unacked messages), a retry from the except
        # block below, or a re-queue from reindex_pending_documents if a run
        # legitimately took longer than REINDEX_STALE_AFTER. Without clearing
        # any prior chunks first, a second run would just append a second copy
        # of every chunk into FAISS - same passages returned twice in search
        # results, and an inflanted chunk count. delete_document() is a no-op
        # (returns 0) the first time thi document has never been indexed, so
        # this is always safe to call.
        get_store().delete_document(document_id,owner_id=str(document.owner_id))
        get_store().add(document_id,chunks,vectors,owner_id=str(document.owner_id))

        document.status=DocumentStatus.PROCESSED.value
        document.chunk_count=len(chunks)
        session.commit()

        celery_app.send_task(TOPIC_DOCUMENT_PROCESSED,args=[document_id])
        publish_document_status(str(document.owner_id),{
            "document_id":document_id,
            "status":DocumentStatus.PROCESSED.value,
            "chunk_count":len(chunks),
        })
        logger.info("process_document:completed",document_id=document_id,chunks=len(chunks))
    except Exception as exc:
        session.rollback()
        document=session.get(Document,UUID(document_id))
        if document is not None:
            document.status=DocumentStatus.FAILED.value
            document.error_message=str(exc)
            session.commit()
            publish_document_status(str(document.owner_id),{
                "document_id":document_id,
                "status":DocumentStatus.FAILED.value,
                "error_message":str(exc),
            })
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
        cutoff=utc_now() - REINDEX_STALE_AFTER
        stuck = (
            session.query(Document)
            .filter(Document.status.in_([DocumentStatus.PENDING.value,DocumentStatus.PROCESSING.value]),Document.updated_at < cutoff)
            .all()
        )
        for document in stuck:
            logger.info("reindex_pending_documents: re-queueing",document_id=str(document.id))
            celery_app.send_task(TOPIC_DOCUMENT_UPLOADED,args=[str(document.id)])
    finally:
        session.close()
        
