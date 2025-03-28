"""Utilities for formatting function and class signatures."""

import inspect
from collections.abc import Callable


def get_signature_params(obj: type | Callable) -> list[str]:
    """Get parameter names from an object's signature.

    Args:
        obj: Class or function to get parameters from

    Returns:
        List of parameter names
    """
    try:
        sig = inspect.signature(obj)
        return [
            name
            for name, param in sig.parameters.items()
            if param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD)
        ]
    except ValueError:
        return []


def format_signature(obj: type | Callable) -> str:
    """Format object signature with parameter types.

    Args:
        obj: Class or function to format signature for

    Returns:
        Formatted signature string
    """
    try:
        sig = inspect.signature(obj)
        return f"{obj.__name__}{sig}"
    except ValueError:
        return obj.__name__
