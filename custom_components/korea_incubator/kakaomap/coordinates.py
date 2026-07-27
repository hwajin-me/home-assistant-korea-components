"""Coordinate system conversion utilities for KakaoMap integration."""

import math
from typing import Dict, Tuple


class CoordinateConverter:
    """Coordinate system converter for various Korean coordinate systems."""

    # 타원체 상수들
    ELLIPSOID_GRS80 = {
        "a": 6378137.0,  # 장반경
        "f": 1 / 298.257222101,  # 편평률
    }

    ELLIPSOID_BESSEL = {
        "a": 6377397.155,  # 장반경
        "f": 1 / 299.1528128,  # 편평률
    }

    # 좌표계 변환 파라미터
    TRANSFORM_PARAMS = {
        "dx": -115.80,
        "dy": 474.99,
        "dz": 674.11,
        "wx": 1.16 * math.pi / (180 * 3600),
        "wy": -2.31 * math.pi / (180 * 3600),
        "wz": -1.63 * math.pi / (180 * 3600),
        "k": -6.43e-6,
    }

    # 중부원점TM 투영 파라미터
    KOREA_TM_CENTRAL = {
        "longitude_of_origin": 127.0,  # 중앙경선
        "latitude_of_origin": 38.0,  # 원점위도
        "scale_factor": 0.9996,  # 축척계수
        "false_easting": 200000.0,  # 가산값 동쪽
        "false_northing": 500000.0,  # 가산값 북쪽
    }

    @classmethod
    def wgs84_to_wcongnamul(
        cls, longitude: float, latitude: float
    ) -> Tuple[float, float]:
        """
        WGS84 좌표를 WCONGNAMUL (중부원점TM) 좌표로 변환

        Args:
            longitude: WGS84 경도
            latitude: WGS84 위도

        Returns:
            (x, y): WCONGNAMUL 좌표계의 (x, y)
        """
        # 1단계: WGS84 -> GRS80 (한국측지계)
        grs80_coords = cls._wgs84_to_grs80(longitude, latitude)

        # 2단계: GRS80 -> 중부원점TM
        tm_coords = cls._geodetic_to_tm(grs80_coords[0], grs80_coords[1])

        return tm_coords

    @classmethod
    def wcongnamul_to_wgs84(cls, x: float, y: float) -> Tuple[float, float]:
        """
        WCONGNAMUL (중부원점TM) 좌표를 WGS84 좌표로 변환

        Args:
            x: WCONGNAMUL X 좌표
            y: WCONGNAMUL Y 좌표

        Returns:
            (longitude, latitude): WGS84 좌표계의 (경도, 위도)
        """
        # 1단계: 중부원점TM -> GRS80
        geodetic_coords = cls._tm_to_geodetic(x, y)

        # 2단계: GRS80 -> WGS84
        wgs84_coords = cls._grs80_to_wgs84(geodetic_coords[0], geodetic_coords[1])

        return wgs84_coords

    @classmethod
    def _wgs84_to_grs80(cls, longitude: float, latitude: float) -> Tuple[float, float]:
        """WGS84를 GRS80으로 변환 (7매개변수 변환)"""
        # 도를 라디안으로 변환
        lon_rad = math.radians(longitude)
        lat_rad = math.radians(latitude)

        # WGS84 타원체 상수
        a = cls.ELLIPSOID_GRS80["a"]
        f = cls.ELLIPSOID_GRS80["f"]
        e2 = 2 * f - f * f

        # 법선의 곡률반지름
        N = a / math.sqrt(1 - e2 * math.sin(lat_rad) ** 2)

        # 직교좌표 변환
        X = N * math.cos(lat_rad) * math.cos(lon_rad)
        Y = N * math.cos(lat_rad) * math.sin(lon_rad)
        Z = N * (1 - e2) * math.sin(lat_rad)

        # 7매개변수 변환
        params = cls.TRANSFORM_PARAMS
        X_new = (
            params["dx"] + (1 + params["k"]) * X + params["wz"] * Y - params["wy"] * Z
        )
        Y_new = (
            params["dy"] - params["wz"] * X + (1 + params["k"]) * Y + params["wx"] * Z
        )
        Z_new = (
            params["dz"] + params["wy"] * X - params["wx"] * Y + (1 + params["k"]) * Z
        )

        # 다시 지리좌표로 변환
        p = math.sqrt(X_new**2 + Y_new**2)
        theta = math.atan(Z_new * a / (p * a * (1 - f)))

        lat_new = math.atan(
            (Z_new + e2 * a * (1 - f) * math.sin(theta) ** 3)
            / (p - e2 * a * math.cos(theta) ** 3)
        )
        lon_new = math.atan2(Y_new, X_new)

        return (math.degrees(lon_new), math.degrees(lat_new))

    @classmethod
    def _grs80_to_wgs84(cls, longitude: float, latitude: float) -> Tuple[float, float]:
        """GRS80을 WGS84로 변환 (역변환)"""
        # 역변환 파라미터 (부호 반대)
        lon_rad = math.radians(longitude)
        lat_rad = math.radians(latitude)

        a = cls.ELLIPSOID_GRS80["a"]
        f = cls.ELLIPSOID_GRS80["f"]
        e2 = 2 * f - f * f

        N = a / math.sqrt(1 - e2 * math.sin(lat_rad) ** 2)

        X = N * math.cos(lat_rad) * math.cos(lon_rad)
        Y = N * math.cos(lat_rad) * math.sin(lon_rad)
        Z = N * (1 - e2) * math.sin(lat_rad)

        # 역변환 파라미터
        params = cls.TRANSFORM_PARAMS
        X_new = (
            -params["dx"] + (1 - params["k"]) * X - params["wz"] * Y + params["wy"] * Z
        )
        Y_new = (
            -params["dy"] + params["wz"] * X + (1 - params["k"]) * Y - params["wx"] * Z
        )
        Z_new = (
            -params["dz"] - params["wy"] * X + params["wx"] * Y + (1 - params["k"]) * Z
        )

        p = math.sqrt(X_new**2 + Y_new**2)
        theta = math.atan(Z_new * a / (p * a * (1 - f)))

        lat_new = math.atan(
            (Z_new + e2 * a * (1 - f) * math.sin(theta) ** 3)
            / (p - e2 * a * math.cos(theta) ** 3)
        )
        lon_new = math.atan2(Y_new, X_new)

        return (math.degrees(lon_new), math.degrees(lat_new))

    @classmethod
    def _geodetic_to_tm(cls, longitude: float, latitude: float) -> Tuple[float, float]:
        """지리좌표를 중부원점TM 좌표로 변환"""
        params = cls.KOREA_TM_CENTRAL
        a = cls.ELLIPSOID_GRS80["a"]
        f = cls.ELLIPSOID_GRS80["f"]

        # 매개변수 계산
        e2 = 2 * f - f * f
        e4 = e2 * e2
        e6 = e4 * e2

        lat_rad = math.radians(latitude)
        lon_rad = math.radians(longitude)
        lat0_rad = math.radians(params["latitude_of_origin"])
        lon0_rad = math.radians(params["longitude_of_origin"])

        k0 = params["scale_factor"]

        # 보조 함수들
        A = a * (1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256)
        B = a * (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024)
        C = a * (15 * e4 / 256 + 45 * e6 / 1024)
        D = a * (35 * e6 / 3072)

        # 자오선호장
        M = (
            A * lat_rad
            - B * math.sin(2 * lat_rad)
            + C * math.sin(4 * lat_rad)
            - D * math.sin(6 * lat_rad)
        )
        M0 = (
            A * lat0_rad
            - B * math.sin(2 * lat0_rad)
            + C * math.sin(4 * lat0_rad)
            - D * math.sin(6 * lat0_rad)
        )

        # 보조 변수들
        nu = a / math.sqrt(1 - e2 * math.sin(lat_rad) ** 2)
        rho = a * (1 - e2) / (1 - e2 * math.sin(lat_rad) ** 2) ** (3 / 2)
        eta2 = nu / rho - 1

        p = lon_rad - lon0_rad

        # TM 투영 공식
        T = math.tan(lat_rad) ** 2
        C = e2 * math.cos(lat_rad) ** 2 / (1 - e2)

        x = (
            k0
            * nu
            * (
                p
                + (1 - T + C) * p**3 / 6
                + (5 - 18 * T + T**2 + 72 * C - 58 * eta2) * p**5 / 120
            )
        )
        y = k0 * (
            M
            - M0
            + nu
            * math.tan(lat_rad)
            * (
                p**2 / 2
                + (5 - T + 9 * C + 4 * C**2) * p**4 / 24
                + (61 - 58 * T + T**2 + 600 * C - 330 * eta2) * p**6 / 720
            )
        )

        # 가산값 적용
        x += params["false_easting"]
        y += params["false_northing"]

        return (x, y)

    @classmethod
    def _tm_to_geodetic(cls, x: float, y: float) -> Tuple[float, float]:
        """중부원점TM 좌표를 지리좌표로 변환"""
        params = cls.KOREA_TM_CENTRAL
        a = cls.ELLIPSOID_GRS80["a"]
        f = cls.ELLIPSOID_GRS80["f"]

        # 가산값 제거
        x -= params["false_easting"]
        y -= params["false_northing"]

        e2 = 2 * f - f * f
        e4 = e2 * e2
        e6 = e4 * e2

        k0 = params["scale_factor"]
        lat0_rad = math.radians(params["latitude_of_origin"])
        lon0_rad = math.radians(params["longitude_of_origin"])

        # 보조 함수들
        A = a * (1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256)
        B = a * (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024)
        C = a * (15 * e4 / 256 + 45 * e6 / 1024)
        D = a * (35 * e6 / 3072)

        M0 = (
            A * lat0_rad
            - B * math.sin(2 * lat0_rad)
            + C * math.sin(4 * lat0_rad)
            - D * math.sin(6 * lat0_rad)
        )
        M = M0 + y / k0

        # 위도 근사값 계산
        mu = M / (a * (1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256))
        lat1 = (
            mu
            + (3 / 2 * e2 - 27 / 32 * e4) * math.sin(2 * mu)
            + (21 / 16 * e4 - 55 / 32 * e6) * math.sin(4 * mu)
            + 151 / 96 * e6 * math.sin(6 * mu)
        )

        # 보조 변수들
        nu1 = a / math.sqrt(1 - e2 * math.sin(lat1) ** 2)
        rho1 = a * (1 - e2) / (1 - e2 * math.sin(lat1) ** 2) ** (3 / 2)
        T1 = math.tan(lat1) ** 2
        C1 = e2 * math.cos(lat1) ** 2 / (1 - e2)
        eta1_2 = nu1 / rho1 - 1
        D_var = x / (nu1 * k0)

        # 위도 계산
        lat = lat1 - (nu1 * math.tan(lat1) / rho1) * (
            D_var**2 / 2
            - (5 + 3 * T1 + 10 * C1 - 4 * C1**2 - 9 * eta1_2) * D_var**4 / 24
            + (61 + 90 * T1 + 298 * C1 + 45 * T1**2 - 252 * eta1_2 - 3 * C1**2)
            * D_var**6
            / 720
        )

        # 경도 계산
        lon = lon0_rad + (
            D_var
            - (1 + 2 * T1 + C1) * D_var**3 / 6
            + (5 - 2 * C1 + 28 * T1 - 3 * C1**2 + 8 * eta1_2 + 24 * T1**2)
            * D_var**5
            / 120
        ) / math.cos(lat1)

        return (math.degrees(lon), math.degrees(lat))


def convert_coordinates(
    coords: Dict[str, float], from_system: str, to_system: str
) -> Dict[str, float]:
    """
    좌표계 간 변환을 수행하는 편의 함수

    Args:
        coords: {'x': float, 'y': float} 또는 {'longitude': float, 'latitude': float}
        from_system: 원본 좌표계 ('WGS84' 또는 'WCONGNAMUL')
        to_system: 대상 좌표계 ('WGS84' 또는 'WCONGNAMUL')

    Returns:
        변환된 좌표 딕셔너리
    """
    if from_system == to_system:
        return coords.copy()

    if from_system == "WGS84" and to_system == "WCONGNAMUL":
        x, y = CoordinateConverter.wgs84_to_wcongnamul(
            coords.get("longitude", coords.get("x", 0)),
            coords.get("latitude", coords.get("y", 0)),
        )
        return {"x": x, "y": y}

    elif from_system == "WCONGNAMUL" and to_system == "WGS84":
        longitude, latitude = CoordinateConverter.wcongnamul_to_wgs84(
            coords.get("x", 0), coords.get("y", 0)
        )
        return {"longitude": longitude, "latitude": latitude}

    else:
        raise ValueError(f"Unsupported conversion: {from_system} to {to_system}")


def validate_coordinates(coords: Dict[str, float], coord_system: str) -> bool:
    """
    좌표가 유효한 범위에 있는지 확인

    Args:
        coords: 좌표 딕셔너리
        coord_system: 좌표계 ('WGS84' 또는 'WCONGNAMUL')

    Returns:
        유효성 여부
    """
    if coord_system == "WGS84":
        longitude = coords.get("longitude", coords.get("x", 0))
        latitude = coords.get("latitude", coords.get("y", 0))

        # 한국 지역 대략적 범위
        return (124.0 <= longitude <= 132.0) and (33.0 <= latitude <= 39.0)

    elif coord_system == "WCONGNAMUL":
        x = coords.get("x", 0)
        y = coords.get("y", 0)

        # 중부원점TM 좌표계의 한국 지역 대략적 범위
        return (100000 <= x <= 600000) and (1000000 <= y <= 1500000)

    return False
