"""Routes for geospatial file uploads, metadata, and measurements."""

import json
import logging
from pathlib import Path
import shutil
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import GeoFile, Measurement
from app.schemas import (
    ErrorResponse,
    FileMetadataResponse,
    FileUploadResponse,
    MeasurementResponse,
)
from app.services.geospatial import process_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["Files"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".zip", ".kml"}


def _validate_file_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return ext


@router.post(
    "/",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    _validate_file_extension(file.filename or "")

    file_id = str(uuid.uuid4())
    saved_filename = f"{file_id}_{file.filename}"
    file_path = UPLOAD_DIR / saved_filename

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as exc:
        logger.exception("Failed to save uploaded file")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save file to disk: {exc}",
        )

    geo_file = GeoFile(id=file_id, filename=file.filename, status="PENDING")
    db.add(geo_file)
    await db.flush()

    try:
        result = process_file(file_path)
    except ValueError as exc:
        geo_file.status = "FAILED"
        geo_file.error_message = str(exc)
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Error processing geospatial file")
        geo_file.status = "FAILED"
        geo_file.error_message = str(exc)
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process geospatial file: {exc}",
        )

    geo_file.feature_count = result.feature_count
    geo_file.crs = result.crs
    geo_file.status = "COMPLETED"

    for m in result.measurements:
        meas = Measurement(
            file_id=file_id,
            feature_index=m.feature_index,
            geometry_type=m.geometry_type,
            measurement_type=m.measurement_type,
            measurement_value=m.measurement_value,
            properties=json.dumps(m.properties) if m.properties else None,
        )
        db.add(meas)

    await db.flush()

    return FileUploadResponse(
        id=file_id,
        message="File processed successfully.",
    )


@router.get(
    "/{file_id}/",
    response_model=FileMetadataResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_file_metadata(
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    query = await db.execute(select(GeoFile).where(GeoFile.id == file_id))
    geo_file = query.scalar_one_or_none()

    if geo_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with id '{file_id}' not found.",
        )

    return FileMetadataResponse(
        id=geo_file.id,
        filename=geo_file.filename,
        feature_count=geo_file.feature_count,
        crs=geo_file.crs,
        status=geo_file.status,
    )


@router.get(
    "/{file_id}/measurements/",
    response_model=list[MeasurementResponse],
    responses={404: {"model": ErrorResponse}},
)
async def get_file_measurements(
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    file_query = await db.execute(select(GeoFile).where(GeoFile.id == file_id))
    if file_query.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with id '{file_id}' not found.",
        )

    meas_query = await db.execute(
        select(Measurement)
        .where(Measurement.file_id == file_id)
        .order_by(Measurement.feature_index)
    )
    rows = meas_query.scalars().all()

    return [
        MeasurementResponse(
            feature_index=r.feature_index,
            geometry_type=r.geometry_type,
            measurement_type=r.measurement_type,
            measurement_value=r.measurement_value,
            properties=json.loads(r.properties) if r.properties else None,
        )
        for r in rows
    ]
