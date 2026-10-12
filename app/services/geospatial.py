"""Service for reading geospatial files and computing measurements."""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import tempfile
from typing import Any, Optional
import zipfile

import fiona
import fiona.drvsupport
import geopandas as gpd
from pyproj import CRS

from app.services.crs_utils import project_to_utm

logger = logging.getLogger(__name__)

# Fiona doesn't enable KML driver by default
fiona.drvsupport.supported_drivers["KML"] = "rw"
fiona.drvsupport.supported_drivers["LIBKML"] = "rw"

AREA_GEOMETRIES = {"Polygon", "MultiPolygon"}
LENGTH_GEOMETRIES = {"LineString", "MultiLineString"}


@dataclass
class FeatureMeasurement:
    feature_index: int
    geometry_type: Optional[str]
    measurement_type: Optional[str]
    measurement_value: Optional[float]
    properties: Optional[dict[str, Any]]


@dataclass
class ProcessingResult:
    crs: Optional[str]
    feature_count: int
    measurements: list[FeatureMeasurement]


def _read_shapefile_zip(file_path: Path) -> gpd.GeoDataFrame:
    try:
        return gpd.read_file(f"zip://{file_path}")
    except Exception:
        # If shapefile is nested in subfolders inside the zip, extract and look for .shp
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(file_path, "r") as zf:
                zf.extractall(tmp_dir)

            shp_files = list(Path(tmp_dir).rglob("*.shp"))
            if not shp_files:
                raise ValueError("No .shp file found inside the uploaded zip archive.")

            return gpd.read_file(shp_files[0])


def _read_kml(file_path: Path) -> gpd.GeoDataFrame:
    return gpd.read_file(file_path, driver="KML")


def read_geospatial_file(file_path: Path) -> gpd.GeoDataFrame:
    suffix = file_path.suffix.lower()
    if suffix == ".zip":
        return _read_shapefile_zip(file_path)
    elif suffix == ".kml":
        return _read_kml(file_path)
    raise ValueError(f"Unsupported format '{suffix}'. Only .zip and .kml are supported.")


def _measure_feature(geom, source_crs):
    if geom is None or geom.is_empty:
        return None, None, None

    geom_type = geom.geom_type
    if geom_type in AREA_GEOMETRIES:
        projected = project_to_utm(geom, source_crs)
        return geom_type, "area", projected.area

    if geom_type in LENGTH_GEOMETRIES:
        projected = project_to_utm(geom, source_crs)
        return geom_type, "length", projected.length

    # Points or other non-measurable types
    return geom_type, None, None


def _clean_properties(row_dict: dict[str, Any]) -> dict[str, Any]:
    props = {k: v for k, v in row_dict.items() if k != "geometry"}
    clean = {}
    for k, v in props.items():
        try:
            json.dumps(v)
            clean[k] = v
        except (TypeError, ValueError):
            clean[k] = str(v)
    return clean


def process_file(file_path: Path) -> ProcessingResult:
    gdf = read_geospatial_file(file_path)

    if gdf.crs is not None:
        source_crs = gdf.crs
        try:
            epsg = gdf.crs.to_epsg()
            crs_str = f"EPSG:{epsg}" if epsg else str(gdf.crs)
        except Exception:
            crs_str = str(gdf.crs)
    else:
        # Default to WGS 84 if CRS is not defined (standard for KML)
        source_crs = CRS.from_epsg(4326)
        crs_str = "EPSG:4326"

    measurements = []
    for idx, row in gdf.iterrows():
        geom_type, m_type, m_val = _measure_feature(row.geometry, source_crs)
        feature_idx = int(idx) if isinstance(idx, (int, float)) else len(measurements)

        measurements.append(
            FeatureMeasurement(
                feature_index=feature_idx,
                geometry_type=geom_type,
                measurement_type=m_type,
                measurement_value=round(m_val, 4) if m_val is not None else None,
                properties=_clean_properties(row.to_dict()),
            )
        )

    return ProcessingResult(
        crs=crs_str,
        feature_count=len(gdf),
        measurements=measurements,
    )
