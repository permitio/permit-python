from typing import Any, Dict

from .dicts import deep_merge

Context = Dict[str, Any]


class ContextStore:
    def __init__(self):
        self._base_context: Context = {}

    def add(self, context: Context):
        self._base_context = deep_merge(self._base_context, context)

    def get_derived_context(self, context: Context) -> Context:
        return deep_merge(self._base_context, context)
