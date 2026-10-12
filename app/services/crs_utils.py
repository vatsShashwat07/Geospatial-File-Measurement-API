"""Utilities for handling Coordinate Reference System (CRS) transformations."""

import math
from pyproj import CRS, Transformer
from shapely.ops import transform


def get_utm_crs(lat: float, lon: float) -> CRS:
    """
    Find the appropriate UTM CRS for a given latitude and longitude.
    UTM divides the world into 60 zones of 6 degrees longitude each:
      - zone = floor((lon + 180) / 6) + 1
      - EPSG: 326xx for northern hemisphere, 327xx for southern hemisphere.
    """
    zone = int(math.floor((lon + 180) / 6)) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def project_to_utm(geom, source_crs=None):
    """
    Reproject geometry from geographic coordinates (degrees) to local UTM (meters)
    based on the geometry's centroid, so area and length calculations are accurate.
    """
    if source_crs is None:
        source_crs = CRS.from_epsg(4326)
    elif isinstance(source_crs, str):
        source_crs = CRS.from_user_input(source_crs)

    centroid = geom.centroid
    target_crs = get_utm_crs(centroid.y, centroid.x)

    # always_xy=True ensures (x=lon, y=lat) order matches shapely
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return transform(transformer.transform, geom)
