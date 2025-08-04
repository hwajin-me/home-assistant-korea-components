"""Exceptions for GoodsFlow integration."""


class GoodsFlowError(Exception):
    """Base exception for GoodsFlow integration."""


class GoodsFlowAuthError(GoodsFlowError):
    """Authentication error with GoodsFlow."""


class GoodsFlowConnectionError(GoodsFlowError):
    """Connection error with GoodsFlow."""


class GoodsFlowDataError(GoodsFlowError):
    """Data parsing error with GoodsFlow."""
