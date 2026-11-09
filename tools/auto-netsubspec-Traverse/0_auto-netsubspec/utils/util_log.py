#!/usr/bin/env python3
"""
Logging Utilities

This module provides utility functions for logging.
"""

import logging
from typing import NoReturn

logger = logging.getLogger(__name__)


def verbose_info(verbose: bool, message: str, *args, **kwargs) -> None:
    """Log an INFO message only if verbose is True
    
    Args:
        verbose: If True, log the message; if False, do nothing
        message: Log message format string
        *args: Arguments for message formatting
        **kwargs: Keyword arguments for message formatting
    """
    if verbose:
        logger.info(message, *args, **kwargs)


def verbose_debug(verbose: bool, message: str, *args, **kwargs) -> None:
    """Log a DEBUG message only if verbose is True
    
    Args:
        verbose: If True, log the message; if False, do nothing
        message: Log message format string
        *args: Arguments for message formatting
        **kwargs: Keyword arguments for message formatting
    """
    if verbose:
        logger.debug(message, *args, **kwargs)


def log_info(message: str, *args, **kwargs) -> None:
    """Log an INFO message

    Args:
        message: Log message format string
        *args: Arguments for message formatting
        **kwargs: Keyword arguments for message formatting
    """
    verbose_info(True, message, *args, **kwargs)


def log_debug(message: str, *args, **kwargs) -> None:
    """Log a DEBUG message

    Args:
        message: Log message format string
        *args: Arguments for message formatting
        **kwargs: Keyword arguments for message formatting
    """
    verbose_debug(True, message, *args, **kwargs)

def log_error(message: str, *args, **kwargs) -> NoReturn:
    """Log an ERROR message and exit

    Args:
        message: Log message format string
        *args: Arguments for message formatting
        **kwargs: Keyword arguments for message formatting
    """
    verbose_debug(True, message, *args, **kwargs)
    exit(1)