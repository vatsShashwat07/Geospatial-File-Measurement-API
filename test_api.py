"""
End-to-end integration test: upload KML, fetch metadata, fetch measurements.
"""

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"
KML_PATH = Path(__file__).parent / "test_data.kml"
ZIP_PATH = Path(__file__).parent / "test_data.zip"


def post_file(filepath: Path | None = None, raw_data: bytes = b"", filename: str = "test.txt") -> tuple[int, dict]:
    """Upload a file via multipart/form-data using only stdlib."""
    boundary = "----PythonTestBoundary"
    if filepath is not None:
        filename = filepath.name
        file_data = filepath.read_bytes()
    else:
        file_data = raw_data

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE}/api/files/",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get_json(path: str) -> dict | list:
    with urllib.request.urlopen(f"{BASE}{path}") as resp:
        return json.loads(resp.read())


def main():
    print("=" * 60)
    print("  Geospatial File Measurement API — Integration Test Suite")
    print("=" * 60)

    # 1. Health check GET /
    print("\n[1] GET /  (health check)")
    health = get_json("/")
    print(f"    Response: {health}")
    assert health.get("status") == "ok", "Health check failed!"
    print("    ✓ Health check passed")

    # 2. POST /api/files/ with KML
    print("\n[2] POST /api/files/  (uploading test_data.kml)")
    status_code, result = post_file(KML_PATH)
    print(f"    Response [{status_code}]: {json.dumps(result, indent=2)}")
    assert status_code == 201, f"Expected 201, got {status_code}"
    file_id = result["id"]
    assert result["message"] == "File processed successfully.", "Upload failed!"
    print("    ✓ KML upload succeeded")

    # 3. GET /api/files/{id}/ for KML
    print(f"\n[3] GET /api/files/{file_id}/  (KML metadata)")
    meta = get_json(f"/api/files/{file_id}/")
    print(f"    Response: {json.dumps(meta, indent=2)}")
    assert meta["status"] == "COMPLETED"
    assert meta["feature_count"] == 3
    assert meta["filename"] == "test_data.kml"
    print("    ✓ KML metadata correct (3 features, COMPLETED)")

    # 4. GET /api/files/{id}/measurements/ for KML
    print(f"\n[4] GET /api/files/{file_id}/measurements/  (KML measurements)")
    measurements = get_json(f"/api/files/{file_id}/measurements/")
    print(f"    Response: {json.dumps(measurements, indent=2)}")
    assert len(measurements) == 3

    types = {m["geometry_type"]: m for m in measurements}
    polygon_m = types["Polygon"]
    assert polygon_m["measurement_type"] == "area"
    assert polygon_m["measurement_value"] > 0
    print(f"    ✓ Polygon area = {polygon_m['measurement_value']:.2f} m²")

    line_m = types["LineString"]
    assert line_m["measurement_type"] == "length"
    assert line_m["measurement_value"] > 0
    print(f"    ✓ LineString length = {line_m['measurement_value']:.2f} m")

    point_m = types["Point"]
    assert point_m["measurement_type"] is None
    assert point_m["measurement_value"] is None
    print("    ✓ Point measurement correctly skipped (null)")

    # 5. POST /api/files/ with Shapefile (.zip)
    if ZIP_PATH.exists():
        print("\n[5] POST /api/files/  (uploading test_data.zip - Shapefile)")
        zip_status, zip_result = post_file(ZIP_PATH)
        print(f"    Response [{zip_status}]: {json.dumps(zip_result, indent=2)}")
        assert zip_status == 201, f"Expected 201, got {zip_status}"
        zip_file_id = zip_result["id"]

        # 6. GET metadata for Shapefile
        print(f"\n[6] GET /api/files/{zip_file_id}/  (Shapefile metadata)")
        zip_meta = get_json(f"/api/files/{zip_file_id}/")
        print(f"    Response: {json.dumps(zip_meta, indent=2)}")
        assert zip_meta["status"] == "COMPLETED"
        assert zip_meta["feature_count"] == 2
        print("    ✓ Shapefile metadata correct (2 features, COMPLETED)")

        # 7. GET measurements for Shapefile
        print(f"\n[7] GET /api/files/{zip_file_id}/measurements/  (Shapefile measurements)")
        zip_meas = get_json(f"/api/files/{zip_file_id}/measurements/")
        print(f"    Response: {json.dumps(zip_meas, indent=2)}")
        assert len(zip_meas) == 2
        for m in zip_meas:
            assert m["measurement_type"] == "area"
            assert m["measurement_value"] > 0
        print("    ✓ Shapefile polygon area measurements valid")

    # 8. Test 404 Not Found
    print("\n[8] GET /api/files/nonexistent/  (expecting 404)")
    try:
        get_json("/api/files/nonexistent/")
        print("    ✗ Should have returned 404!")
        sys.exit(1)
    except urllib.error.HTTPError as e:
        assert e.code == 404
        print(f"    ✓ Got expected 404: {json.loads(e.read())['detail']}")

    # 9. Test 400 Bad Request (Unsupported file extension)
    print("\n[9] POST /api/files/ with invalid extension (.txt, expecting 400)")
    bad_status, bad_res = post_file(raw_data=b"dummy text", filename="invalid.txt")
    print(f"    Response [{bad_status}]: {bad_res}")
    assert bad_status == 400
    print(f"    ✓ Got expected 400: {bad_res['detail']}")

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED SUCCESSFULLY ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
