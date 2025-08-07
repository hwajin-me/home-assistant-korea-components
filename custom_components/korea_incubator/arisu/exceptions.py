"""Exceptions for Arisu integration."""


class ArisuError(Exception):
    """Base exception for Arisu integration."""


class ArisuAuthError(ArisuError):
    """Authentication error with Arisu."""


class ArisuConnectionError(ArisuError):
    """Connection error with Arisu."""


class ArisuDataError(ArisuError):
    """Data parsing error with Arisu."""
