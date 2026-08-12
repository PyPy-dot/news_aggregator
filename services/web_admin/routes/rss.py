from fastapi import APIRouter

router = APIRouter()

@router.get('/')
async def list_rss():
    return {'message': 'rss endpoint'}

