from fastapi import APIRouter

router=APIRouter()

@router.get("/")
async def health():
    return {"service":"chat-service","status":"healthy"}