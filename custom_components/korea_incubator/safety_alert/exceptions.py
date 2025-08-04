"""Exceptions for Safety Alert integration."""


class SafetyAlertError(Exception):
    """Base exception for Safety Alert integration."""


class SafetyAlertConnectionError(SafetyAlertError):
    """Connection error with Safety Alert API."""


class SafetyAlertDataError(SafetyAlertError):
    """Data parsing error with Safety Alert API."""
