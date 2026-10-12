"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import init_db
from app.routers.files import router as files_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Make sure DB tables are created on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Geospatial File Measurement API",
    description=(
        "Upload Shapefiles (.zip) or KML files and get area/length "
        "measurements for every feature, computed in the correct UTM projection."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(files_router)


@app.get("/", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "Geospatial File Measurement API"}
