from fastapi import APIRouter

from Controllers.health import get_health
from Models.health_schema import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health():
    return get_health()
