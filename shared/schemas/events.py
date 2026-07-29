from datetime import datetime
from typing import Any
from uuid import UUID,uuid4

from pydantic import BaseModel,Field

from shared.utils.datetime import utc_now

class Event(BaseModel):
    event_id:UUID=Field(default_factory=uuid4)
    topic:str
    timestamp:datetime=Field(default_factory=utc_now)
    payload:dict[str,Any]

TOPIC_DOCUMENT_UPLOADED="document.uploaded"
TOPIC_DOCUMENT_PROCESSED="document.processed"
TOPIC_EMBEDDING_COMPLETED="embedding.completed"
TOPIC_ANALYSIS_COMPLETED="analysis.completed"
