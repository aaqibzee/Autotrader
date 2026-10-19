from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.core.errors import PROBLEM_RESPONSES

api_router = APIRouter(responses=PROBLEM_RESPONSES)
api_router.include_router(health_router)
