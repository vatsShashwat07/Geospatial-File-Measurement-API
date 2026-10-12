# Geospatial File Measurement API

A FastAPI backend service that ingests geospatial files (Shapefiles via `.zip` and `.kml`), handles reprojection from geographic coordinates (WGS 84) to local planar UTM projections, and computes precise area and length measurements for every feature.

Built with **FastAPI**, **GeoPandas**, **PyProj**, **Shapely**, **Fiona**, and **SQLAlchemy** (async SQLite).

---

## Features

- **Multi-Format Ingestion**: Supports ESRI Shapefile archives (`.zip`) and Keyhole Markup Language (`.kml`) files.
- **Dynamic UTM Reprojection**: Automatically calculates the appropriate UTM zone for each geometry based on its centroid to compute real-world metric distances (meters) and areas (square meters).
- **Graceful Geometry Handling**:
  - `Polygon` / `MultiPolygon` &rarr; Area ($m^2$)
  - `LineString` / `MultiLineString` &rarr; Length ($m$)
  - `Point` / `MultiPoint` &rarr; Gracefully records `null` measurement without failing.
- **Asynchronous Persistence**: Uses SQLAlchemy 2.0 with `aiosqlite` to store file metadata and per-feature measurements.
- **Automated Test Suite**: Includes pytest integration tests with programmatic dummy data generation.

---

## Project Structure

```text
Geospatial File Measurement API/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app factory & lifespan
│   ├── database.py          # Async SQLAlchemy engine & session dependency
│   ├── models.py            # ORM models (GeoFile, Measurement)
│   ├── schemas.py           # Pydantic schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   └── files.py         # File upload, metadata, and measurement endpoints
│   └── services/
│       ├── __init__.py
│       ├── crs_utils.py     # Dynamic UTM zone calculation & reprojection
│       └── geospatial.py    # Geospatial parsing & measurement engine
├── tests/
│   ├── __init__.py
│   └── test_api.py          # Pytest suite with mock .kml & .zip fixtures
├── test_api.py              # Standalone end-to-end integration test script
├── test_data.kml            # Sample KML dataset
├── test_data.zip            # Sample Shapefile zip dataset
├── requirements.txt         # Project dependencies
├── .gitignore               # Standard Python gitignore
└── README.md
```

---

## Setup & Installation

### Prerequisites

- Python 3.10+
- `pip`

### 1. Clone the repository & create a virtual environment

```bash
git clone <your-repo-url>
cd "Geospatial File Measurement API"

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the development server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Once running:
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/](http://localhost:8000/)

---

## Running Automated Tests

Run the test suite using `pytest`:

```bash
pytest -v
```

This runs programmatic tests that generate temporary Shapefile `.zip` and `.kml` files on the fly and verify:
- Health check
- KML file upload, metadata parsing, and measurements
- Zipped Shapefile upload, extraction, and measurements
- 404 responses for nonexistent IDs
- 400 validation responses for unsupported file types

Alternatively, run the standalone integration script against a running server:

```bash
python test_api.py
```

---

## API Endpoints

### 1. Health Check
`GET /`
- **Response**: `{"status": "ok", "service": "Geospatial File Measurement API"}`

### 2. Upload Geospatial File
`POST /api/files/`
- **Content-Type**: `multipart/form-data`
- **Form Field**: `file` (a `.zip` containing shapefile components or a `.kml` file)
- **Response** (`201 Created`):
```json
{
  "id": "e3b0c442-98fc-1c14-9afb-4c7b8e19c6e3",
  "message": "File processed successfully."
}
```

### 3. Get File Metadata
`GET /api/files/{file_id}/`
- **Response** (`200 OK`):
```json
{
  "id": "e3b0c442-98fc-1c14-9afb-4c7b8e19c6e3",
  "filename": "survey.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

### 4. Get Measurements
`GET /api/files/{file_id}/measurements/`
- **Response** (`200 OK`):
```json
[
  {
    "feature_index": 0,
    "geometry_type": "Polygon",
    "measurement_type": "area",
    "measurement_value": 1084234.3074,
    "properties": {
      "Name": "Parcel Boundary"
    }
  },
  {
    "feature_index": 1,
    "geometry_type": "LineString",
    "measurement_type": "length",
    "measurement_value": 1478.3324,
    "properties": {
      "Name": "Access Road"
    }
  },
  {
    "feature_index": 2,
    "geometry_type": "Point",
    "measurement_type": null,
    "measurement_value": null,
    "properties": {
      "Name": "Reference Marker"
    }
  }
]
```

---

## Architecture Decisions

1. **FastAPI & Async SQLite (`aiosqlite`)**:
   - Chosen for asynchronous request handling and clean OpenAPI schema generation without external database overhead during local development and testing.
2. **Dynamic UTM Reprojection**:
   - Geometries stored in geographic coordinate systems (like WGS 84 / EPSG:4326) measure coordinates in degrees. Calculating Euclidean area or length in degrees yields distorted values.
   - For each feature, we identify its centroid longitude and determine the corresponding 6-degree UTM zone:
     $$\text{Zone} = \lfloor(\text{Longitude} + 180) / 6\rfloor + 1$$
   - The geometry is dynamically projected into its local UTM zone (`EPSG:326xx` North / `EPSG:327xx` South) using `pyproj.Transformer`, ensuring measurements are accurate in meters and square meters.
3. **Resilient Shapefile Archive Extraction**:
   - GeoPandas `zip://` is used first. If an uploaded `.zip` encapsulates the Shapefile inside nested subdirectories, an automatic fallback extracts the archive to a temporary directory and identifies the primary `.shp` file.
4. **Fiona Driver Registration**:
   - Fiona does not enable the KML driver by default; our service enables `KML` and `LIBKML` drivers upon import to ensure seamless `.kml` parsing.

---

## Learnings and Future Scope

### Key Learnings
- **Geodetic vs Planar CRS**: Working with GIS data requires handling the distinction between ellipsoidal models and projected Cartesian coordinates. Dynamically selecting the local UTM projection per feature centroid allows measuring arbitrary geometries anywhere in the world without hardcoding regional projections.
- **Heterogeneous vs Homogeneous Formats**: KML files naturally allow mixed geometry types (Points, Lines, Polygons in one layer), whereas Shapefiles enforce a single geometry type per layer. The parsing engine accounts for both structures gracefully.

### Future Scope
1. **Background Processing with Celery & Redis**:
   - For large multi-gigabyte shapefiles or complex datasets with thousands of vertices, parsing synchronously in the request-response cycle can cause timeouts. A task queue (Celery/RQ with Redis) will process files asynchronously in worker containers while clients poll the `/api/files/{id}/` endpoint for status changes (`PENDING` &rarr; `PROCESSING` &rarr; `COMPLETED`).
2. **PostGIS Integration**:
   - Migrating from SQLite to PostgreSQL + PostGIS will unlock native spatial indexing (R-Tree / GiST), spatial queries (intersections, buffers, distance matrices), and fast database-level measurements (`ST_Area(geography)`).
3. **GeoJSON & Vector Tile Export**:
   - Add endpoints to export processed files as GeoJSON FeatureCollections or serve them as vector tiles (MVT) for direct rendering on web maps (Mapbox GL / Leaflet).
4. **Geometry Validation & Repair**:
   - Integrate `shapely.validation.make_valid` to automatically fix invalid geometries (such as bowtie polygons or self-intersecting rings) prior to projection.

---

## Author

**Shashwat Pandey**
