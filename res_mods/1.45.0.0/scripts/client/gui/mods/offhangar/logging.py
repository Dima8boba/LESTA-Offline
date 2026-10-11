# -*- coding: utf-8 -*-
"""Logging helpers for OffHangar mod."""

import functools

from gui.mods.offhangar.utils import doLog

__all__ = (
    'doLog',
    'LOG_NOTE',
    'LOG_DEBUG',
)

doLog = functools.partial(doLog, 'OFFHANGAR')
LOG_NOTE = functools.partial(doLog, '[NOTE]')
LOG_DEBUG = functools.partial(doLog, '[DEBUG]')