from fastapi import APIRouter

router = APIRouter()

@router.get('/')
async def list_settings():
    return {'message': 'settings endpoint'}

