from copy import deepcopy
from typing import Any


def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge two dicts recursively, without modifying either of them.

    Args:
        base: The dict to start from.
        overrides: Values that take precedence over `base`. Nested dicts are merged
            key by key; any other value replaces what `base` has.

    Returns:
        A new dict holding the merged result.
    """
    result = base.copy()  # create a clean copy of base
    for key in overrides:  # noqa: PLC0206 - reads overrides[key] as before (dict subclasses)
        if key not in result or not isinstance(result[key], dict):
            result[key] = deepcopy(overrides[key])
        else:
            result[key] = deep_merge(result[key], overrides[key])
    return result
