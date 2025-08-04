"""Exceptions for KakaoMap integration."""


class KakaoMapError(Exception):
    """Base exception for KakaoMap integration."""


class KakaoMapConnectionError(KakaoMapError):
    """Connection error with KakaoMap."""


class KakaoMapDataError(KakaoMapError):
    """Data parsing error with KakaoMap."""


class KakaoMapQuotaError(KakaoMapError):
    """API quota exceeded error with KakaoMap."""
