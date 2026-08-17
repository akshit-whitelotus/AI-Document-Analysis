from typing import Annotated
from uuid import UUID

from fastapi import APIRouter,Depends
from fastapi.concurrency import run_in_threadpool

from shared.messaging.celery_app import celery_app
from shared.security.oauth import AdminUserDep

from app.dependencies.repository import get_document_service
from app.schemas.admin import QueueStatsResponse
from app.schemas.document import DocumentResponse
from app.services.document_service import DocumentService

router=APIRouter()

DocumentServiceDep=Annotated[DocumentService,Depends(get_document_service)]

# Default queue name - celer_app (shared/messaging/celery_app.py) never sets 
# a custom task_default_queue, so every task (including document.uploaded, 
# the one this reprocess endpoint re-sends) lans on Celery's built-in
# default queue, named "celery".
DEFAULT_QUEUE_NAME="celery"

@router.post("/reprocess/{document_id}",response_model=DocumentResponse)
async def reprocess_document(document_id:UUID,admin_user:AdminUserDep,document_service:DocumentServiceDep):
    """
    Admin-only. Forces a document back through the embedding pipeline - 
    useful for a document stuck in PROCESSING (crshed worker, restarted
    container mid-task) or one that ended up FAILED after a transient
    error (e.g ai-worker-service was briefly unreachable). See
    DocumentService.admin_reprocess for why this is safe to call more than
    once - process_document() in ai-worker-service clears any previously
    indexed chunks for this document before re-adding them.
    """
    return await document_service.admin_reprocess(document_id)

def _get_queue_stats() -> dict:
    """
    Synchronous by nature (raw AMQP call to declare-passive + a Celery
    control broadcast to every online worker) - always called via 
    run_in_threadpool from the route below, never directly from async code.
    """
    with celery_app.connection_or_acquire() as connection:
        channel=connection.default_channel
        # passive=True: inspect the queue without creating it - if it
        # doesn't exist yet (no task has ever been sent), this raises,
        # which is handled below as "0 pending".
        declared=channel.queue_declare(queue=DEFAULT_QUEUE_NAME,passive=True)
        pending=declared.message_count

    inspector=celery_app.control.inspect(timeout=2.0)
    active=inspector.active() or {}
    reserved = inspector.reserved() or {}

    return {
        "pending_in_queue": pending,
        "active_tasks":sum(len(tasks) for tasks in active.values()),
        "reserved_tasks":sum(len(tasks) for tasks in reserved.values()),
        "workers_online":sorted(active.keys() | reserved.keys())
    }
@router.get("/queue",response_model=QueueStatsResponse)
async def queue_stats(admin_user:AdminUserDep):
    """
    Admin-only. A rough live view of the document-processing backlog:
    - pending_in_queue: tasks sent but not yet picked up by any worker
    - active_tasks / reserved_tasks: tasks a worker curently has in hand 
    (running, or fetched but not yet started - see
    worker_prefetch_multiplier = 1 in celery_app.py, which caps this at 1
    per worker process)
    -workers_online: which Celery worker hostnames responded at all : an 
    empty list here most likely means every worker is down, not that
    there's simply no work to do.
    
    Talks to RabbitMQ and the Celery workers directly (not to 
    ai-worker-service's HTTP API), so this still works even if
    ai-worker-service's FastAPI process itself is unresponsive but its
    Celery worker process is still alive, or vice versa
    """
    try:
        stats=await run_in_threadpool(_get_queue_stats)
    except Exception as exc:
        # Most likely: the default queue has never been declared yet (no
        # document has ever been uploaded), or the broker/workers are
        # unreachable. Either way, report zeros rather than a 500 - "we
        # don't know" is more useful to an admin dashboard rather than an error
        # page, since a broker hicup shouldn't take down this endpoint
        return QueueStatsResponse(
            pending_in_queue=0,
            active_tasks=0,
            reserved_tasks=0,
            workers_online=[],
            error=str(exc)
        )
    return QueueStatsResponse(**stats)