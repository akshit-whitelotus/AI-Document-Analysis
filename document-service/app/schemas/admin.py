from shared.schemas.base import BaseSchema

class QueueStatsResponse(BaseSchema):
    pending_in_queue: int
    active_tasks: int
    reserved_tasks: int
    workers_online: list[str]
    error: str | None=None