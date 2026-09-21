"""Convert the API's EPSG:5174 coordinates to WGS84 for HA map attributes."""

from functools import lru_cache
from math import isfinite

from pyproj import Transformer
from pyproj.exceptions import ProjError


def point_wgs84(point):
    """Validate Kakao's WGS84 point before using it as a missing-GPS fallback."""
    if not isinstance(point, dict):
        return {}
    try:
        lat, lon = point["lat"], point["lon"]
        if isinstance(lat, bool) or isinstance(lon, bool):
            return {}
        lat, lon = float(lat), float(lon)
        if 32 <= lat <= 39.5 and 124 <= lon <= 132:
            return {"latitude": round(lat, 6), "longitude": round(lon, 6)}
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    return {}


@lru_cache(maxsize=1)
def _transformer():
    """Reuse the CRS/datum transformation; preserve X/easting, Y/northing order."""
    return Transformer.from_crs(
        "EPSG:5174", "EPSG:4326", always_xy=True, allow_ballpark=False
    )


def to_wgs84(x, y) -> dict[str, float]:
    """Return valid Korean latitude/longitude, never fabricated zero coordinates."""
    if isinstance(x, bool) or isinstance(y, bool):
        return {}
    try:
        easting = float(str(x).strip().replace(",", ""))
        northing = float(str(y).strip().replace(",", ""))
        if (
            not isfinite(easting)
            or not isfinite(northing)
            or (easting, northing) == (0, 0)
        ):
            return {}
        longitude, latitude = _transformer().transform(easting, northing, errcheck=True)
    except (ValueError, TypeError, OverflowError, ProjError):
        return {}
    # These datasets contain South Korean facilities. Reject bad source values
    # rather than swapping axes or guessing a different CRS.
    if not (124 <= longitude <= 132 and 32 <= latitude <= 39.5):
        return {}
    return {"latitude": round(latitude, 6), "longitude": round(longitude, 6)}
