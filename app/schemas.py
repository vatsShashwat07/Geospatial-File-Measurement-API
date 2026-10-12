"""Pydantic response schemas for the API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class FileUploadResponse(BaseModel):
    id: str
    message: str


class FileMetadataResponse(BaseModel):
    id: str
    filename: str
    feature_count: int
    crs: Optional[str]
    status: str


class MeasurementResponse(BaseModel):
    feature_index: int
    geometry_type: Optional[str]
    measurement_type: Optional[str]
    measurement_value: Optional[float]
    properties: Optional[dict[str, Any]]


class ErrorResponse(BaseModel):
    detail: str
