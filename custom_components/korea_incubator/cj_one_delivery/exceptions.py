"""CJ O-NE 배송조회 통합구성요소 예외."""


class CJOneDeliveryError(Exception):
    """CJ O-NE 배송조회 기본 예외."""


class CannotConnect(CJOneDeliveryError):
    """앱 API에 연결할 수 없을 때 발생하는 예외."""


class InvalidAuth(CJOneDeliveryError):
    """앱 API에서 인증 정보를 거부했을 때 발생하는 예외."""
