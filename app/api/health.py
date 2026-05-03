from datetime import datetime, timezone
from fastapi import APIRouter
from app.models import HealthResponse, MetadataResponse

router = APIRouter()


@router.get("/v1/healthz", response_model=HealthResponse)
async def healthz():
    return HealthResponse(
        status="ok",
        ts=datetime.now(timezone.utc).isoformat(),
        version="1.0.0",
    )


@router.get("/v1/metadata", response_model=MetadataResponse)
async def metadata():
    return MetadataResponse(
        name="Vera",
        version="1.0.0",
        model="gemini-1.5-pro",
        supported_categories=["dentists", "salons", "restaurants", "gyms", "pharmacies"],
        supported_triggers=["recall", "spike", "dip", "research", "festival", "campaign", "review"],
        endpoints=[
            "POST /v1/context",
            "POST /v1/tick",
            "POST /v1/reply",
            "GET /v1/healthz",
            "GET /v1/metadata",
        ],
    )


@router.get("/")
async def root():
    return {"name": "Vera", "status": "running", "docs": "/docs", "healthz": "/v1/healthz"}