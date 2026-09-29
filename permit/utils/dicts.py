from copy import deepcopy
from typing import Dict


def deep_merge(base: Dict, overrides: Dict):
    """
    merges two dicts recursively
    """
    result = base.copy()  # create a clean copy of base
    for key in overrides:
        if key not in result or not isinstance(result[key], dict):
            result[key] = deepcopy(overrides[key])
        else:
            result[key] = deep_merge(result[key], overrides[key])
    return result
