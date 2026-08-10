from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from shared.exceptions.exceptions import AppException

async def app_exception_handler(request:Request,exc:AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error":exc.__class__.__name__,"message":exc.message}
    )

def register_exception_handlers(app:FastAPI) -> None:
    app.add_exception_handler(AppException,app_exception_handler)