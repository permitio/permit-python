import re

import pydantic


def _parse(version: str) -> tuple[int, ...]:
    """Turn a pydantic version string into a tuple of ints, e.g. "2.14.0b2" -> (2, 14, 0).

    Only the leading digits of the first three components count, so a pre-release,
    dev or local suffix does not stop the SDK from importing.

    Raises:
        ValueError: A component does not start with a digit.
    """
    parts = []
    for part in version.split(".")[:3]:
        digits = re.match(r"[0-9]+", part)
        if digits is None:
            msg = f"Cannot parse pydantic version {version!r}: {part!r} does not start with a digit"
            raise ValueError(msg)
        parts.append(int(digits.group()))
    return tuple(parts)


PYDANTIC_VERSION: tuple[int, ...] = _parse(pydantic.__version__)
