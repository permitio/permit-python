from typing import Any, Callable, Dict, List

from .dicts import deep_merge

Context = Dict[str, Any]
ContextTransform = Callable[[Context], Context]


class ContextStore:
    def __init__(self):
        self._base_context: Context = {}
        self._transforms: List[ContextTransform] = []

    def add(self, context: Context):
        self._base_context = deep_merge(self._base_context, context)

    def register_transform(self, transform: ContextTransform):
        self._transforms.append(transform)

    def get_derived_context(self, context: Context) -> Context:
        return deep_merge(self._base_context, context)

    def transform(self, initial_context: Context) -> Context:
        context = initial_context.copy()
        for transform in self._transforms:
            context = transform(context)
        return context
