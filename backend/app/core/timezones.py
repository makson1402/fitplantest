"""Validation of IANA time zone names that come from clients.

`zoneinfo.ZoneInfo` turns the name into a file path, so odd input does not always raise `ZoneInfoNotFoundError`:
a name with control characters or lone surrogates raises `OSError`, a directory such as "America" raises
`IsADirectoryError`, a path such as "../x" raises `ValueError`. A name is therefore checked against the characters
IANA names use before it is looked up, and every lookup failure means "not a time zone".
"""
from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_+\-]*(/[A-Za-z0-9][A-Za-z0-9_+\-]*){0,2}$")
MAX_LENGTH = 64


def load_timezone(name: str) -> ZoneInfo | None:
    """The zone for `name`, or None when `name` is not a valid IANA time zone."""
    if not isinstance(name, str) or len(name) > MAX_LENGTH or not _NAME.match(name):
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):  # OSError covers IsADirectoryError and bad file names
        return None


def is_valid_timezone(name: str) -> bool:
    return load_timezone(name) is not None
