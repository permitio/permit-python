from typing import Any, Dict  # noqa: UP035 - public alias below

from permit.utils.dicts import deep_merge

# Public alias; runtime object kept identical (a `typing` generic, not a builtin one).
Context = Dict[str, Any]  # noqa: UP006


class ContextStore:
    """A base context that is merged into the context of every authorization query."""

    def __init__(self) -> None:
        self._base_context: Context = {}

    def add(self, context: Context) -> None:
        """Deep-merge `context` into the base context.

        Args:
            context: Values to add; they take precedence over what is already stored.
        """
        self._base_context = deep_merge(self._base_context, context)

    def get_derived_context(self, context: Context) -> Context:
        """Build the context for one query: the base context overridden by `context`.

        Args:
            context: The query's own context.

        Returns:
            A new dict; the base context is left unchanged.
        """
        return deep_merge(self._base_context, context)
