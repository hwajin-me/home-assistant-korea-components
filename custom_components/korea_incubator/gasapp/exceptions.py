"""Exceptions for GasApp integration."""


class GasAppError(Exception):
    """Base exception for GasApp integration."""


class GasAppAuthError(GasAppError):
    """Authentication error with GasApp."""


class GasAppConnectionError(GasAppError):
    """Connection error with GasApp."""


class GasAppDataError(GasAppError):
    """Data parsing error with GasApp."""
