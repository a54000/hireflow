from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.normalize import router as normalize_router
from app.api.ontology import router as ontology_router
from app.api.recruiter_review import router as review_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Deterministic recruiting ontology normalization API.",
    )
    app.include_router(health_router)
    app.include_router(normalize_router)
    app.include_router(ontology_router)
    app.include_router(review_router)
    return app


app = create_app()
