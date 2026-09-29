from typing import Any, Dict  # noqa: UP035 - public alias below

from .dicts import deep_merge

# Public alias; runtime object kept identical (a `typing` generic, not a builtin one).
Context = Dict[str, Any]  # noqa: UP006


class ContextStore:
    def __init__(self):
        self._base_context: Context = {}

    def add(self, context: Context):
        self._base_context = deep_merge(self._base_context, context)

    def get_derived_context(self, context: Context) -> Context:
        return deep_merge(self._base_context, context)
