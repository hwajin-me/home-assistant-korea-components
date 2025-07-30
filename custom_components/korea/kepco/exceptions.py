class KepcoApiError(Exception):
    """Base exception for KEPCO API errors."""
    pass


class KepcoAuthError(KepcoApiError):
    """Exception for KEPCO authentication errors."""
    pass
