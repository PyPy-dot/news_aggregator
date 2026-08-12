from fastapi import APIRouter

router = APIRouter()

@router.get('/')
async def list_console():
    return {'message': 'console endpoint'}

