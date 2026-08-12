from fastapi import APIRouter

router = APIRouter()

@router.get('/')
async def list_dashboard():
    return {'message': 'dashboard endpoint'}

