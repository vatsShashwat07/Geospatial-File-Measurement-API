"""SQLAlchemy models for storing uploaded file info and measurements."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def _new_uuid():
    return str(uuid.uuid4())


class GeoFile(Base):
    """Tracks each uploaded geospatial file and its processing status."""

    __tablename__ = "geo_files"

    id = Column(String, primary_key=True, default=_new_uuid)
    filename = Column(String, nullable=False)
    feature_count = Column(Integer, default=0)
    crs = Column(String, nullable=True)
    status = Column(String, default="PENDING")  # PENDING / COMPLETED / FAILED
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    measurements = relationship(
        "Measurement", back_populates="geo_file", cascade="all, delete-orphan"
    )


class Measurement(Base):
    """Stores area/length measurement for a single feature within a file."""

    __tablename__ = "measurements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String, ForeignKey("geo_files.id"), nullable=False)
    feature_index = Column(Integer, nullable=False)
    geometry_type = Column(String, nullable=True)
    measurement_type = Column(String, nullable=True)   # "area" | "length" | null
    measurement_value = Column(Float, nullable=True)    # m² or m
    properties = Column(Text, nullable=True)            # JSON string of feature attrs

    geo_file = relationship("GeoFile", back_populates="measurements")
