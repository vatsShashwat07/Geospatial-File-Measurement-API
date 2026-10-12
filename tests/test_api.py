"""Pytest suite for Geospatial File Measurement API.

Programmatically generates dummy .kml and .zip Shapefiles,
hits API endpoints via FastAPI TestClient, and asserts measurement logic.
"""

import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString, Point, Polygon

from app.main import app

client = TestClient(app)


@pytest.fixture
def dummy_kml_file(tmp_path: Path) -> Path:
    """Generate a temporary dummy KML file with Polygon, LineString, and Point."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Test Fixture Features</name>
    <Placemark>
      <name>Test Field Polygon</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.2090,28.6139,0
              77.2190,28.6139,0
              77.2190,28.6239,0
              77.2090,28.6239,0
              77.2090,28.6139,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Test Highway Line</name>
      <LineString>
        <coordinates>
          77.2090,28.6139,0
          77.2190,28.6239,0
        </coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Survey Benchmark</name>
      <Point>
        <coordinates>77.2090,28.6139,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""
    file_path = tmp_path / "dummy_survey.kml"
    file_path.write_text(kml_content, encoding="utf-8")
    return file_path


@pytest.fixture
def dummy_shapefile_zip(tmp_path: Path) -> Path:
    """Generate a temporary zipped Shapefile containing Polygon parcels."""
    gdf = gpd.GeoDataFrame(
        [
            {
                "name": "Parcel Alpha",
                "geometry": Polygon([(77.2090, 28.6139), (77.2190, 28.6139), (77.2190, 28.6239), (77.2090, 28.6239)]),
            },
            {
                "name": "Parcel Beta",
                "geometry": Polygon([(77.2200, 28.6139), (77.2300, 28.6139), (77.2300, 28.6239), (77.2200, 28.6239)]),
            },
        ],
        crs="EPSG:4326",
    )

    shapefile_dir = tmp_path / "shp_build"
    shapefile_dir.mkdir()
    shp_path = shapefile_dir / "parcels.shp"
    gdf.to_file(shp_path)

    zip_path = tmp_path / "dummy_parcels.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in shapefile_dir.glob("parcels.*"):
            zf.write(f, arcname=f.name)

    return zip_path


def test_health_check():
    """Verify health probe returns 200 OK."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Geospatial File Measurement API"}


def test_kml_upload_and_measurements(dummy_kml_file: Path):
    """Test full flow with KML: upload -> metadata -> measurements."""
    # 1. Upload KML
    with open(dummy_kml_file, "rb") as f:
        upload_resp = client.post(
            "/api/files/",
            files={"file": (dummy_kml_file.name, f, "application/vnd.google-earth.kml+xml")},
        )
    assert upload_resp.status_code == 201
    upload_data = upload_resp.json()
    assert "id" in upload_data
    file_id = upload_data["id"]

    # 2. Check metadata
    meta_resp = client.get(f"/api/files/{file_id}/")
    assert meta_resp.status_code == 200
    meta = meta_resp.json()
    assert meta["id"] == file_id
    assert meta["feature_count"] == 3
    assert meta["status"] == "COMPLETED"
    assert "EPSG:4326" in meta["crs"]

    # 3. Check measurements
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    measurements = meas_resp.json()
    assert len(measurements) == 3

    meas_by_type = {m["geometry_type"]: m for m in measurements}

    # Polygon should have area in m²
    poly = meas_by_type["Polygon"]
    assert poly["measurement_type"] == "area"
    assert poly["measurement_value"] is not None
    assert poly["measurement_value"] > 0

    # LineString should have length in m
    line = meas_by_type["LineString"]
    assert line["measurement_type"] == "length"
    assert line["measurement_value"] is not None
    assert line["measurement_value"] > 0

    # Point should have null measurement
    point = meas_by_type["Point"]
    assert point["measurement_type"] is None
    assert point["measurement_value"] is None


def test_shapefile_zip_upload_and_measurements(dummy_shapefile_zip: Path):
    """Test full flow with Shapefile (.zip): upload -> metadata -> measurements."""
    # 1. Upload zipped shapefile
    with open(dummy_shapefile_zip, "rb") as f:
        upload_resp = client.post(
            "/api/files/",
            files={"file": (dummy_shapefile_zip.name, f, "application/zip")},
        )
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    # 2. Check metadata
    meta_resp = client.get(f"/api/files/{file_id}/")
    assert meta_resp.status_code == 200
    meta = meta_resp.json()
    assert meta["feature_count"] == 2
    assert meta["status"] == "COMPLETED"

    # 3. Check measurements
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    measurements = meas_resp.json()
    assert len(measurements) == 2
    for m in measurements:
        assert m["geometry_type"] == "Polygon"
        assert m["measurement_type"] == "area"
        assert m["measurement_value"] > 0


def test_nonexistent_file_404():
    """Verify 404 for unknown file IDs."""
    resp = client.get("/api/files/random-nonexistent-uuid/")
    assert resp.status_code == 404

    resp_meas = client.get("/api/files/random-nonexistent-uuid/measurements/")
    assert resp_meas.status_code == 404


def test_unsupported_file_extension_400():
    """Verify 400 for unsupported file formats."""
    dummy_data = b"Not a shapefile or kml"
    resp = client.post(
        "/api/files/",
        files={"file": ("unsupported.txt", dummy_data, "text/plain")},
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]
