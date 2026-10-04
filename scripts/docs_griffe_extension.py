"""The Griffe extension the API reference site loads (mkdocs.yml).

Griffe reads the SDK's source without importing it, and mkdocstrings renders what it reads.
This extension makes the site show what a type checker sees:

- Names bound in both branches of an ``if TYPE_CHECKING: ... else: ...`` block. Griffe
  keeps the ``else`` branch's binding, the runtime one; type checkers read the ``if``
  branch, so that is the one documented. This is how the blocking classes get their
  blocking signatures: the SDK defines each at runtime, in the ``else`` branch, as a
  subclass of an async class that a metaclass makes blocking, and its ``if`` branch binds
  the name to a class of the generated stub, ``permit/_sync_types.pyi``. The match is by
  the full path of the name: ``permit.pdp_api.pdp_api_client`` and
  ``permit.api.sync_api_client`` both have a ``SyncRoleAssignmentsApi``, bound to different
  stub classes.
- Deprecations. A function or class decorated with ``permit.utils.deprecation.deprecated``
  or a PEP 702 ``deprecated`` gets the ``deprecated`` label, and its docstring ends with the
  decorator's message, which names the replacement and the release that removes it. The
  stub has no decorators, so each stub method takes the deprecation of the async method it
  is generated from.
- Context managers. A generator function decorated with ``contextlib.contextmanager``, such
  as ``Permit.wait_for_sync()``, is annotated with the generator it is written as, but calling
  it returns a context manager: a type checker sees ``contextlib._GeneratorContextManager``.
  Its return type shows as ``contextlib.AbstractContextManager``, that class's public base,
  of the type the generator yields.
- pydantic v1 models. The ``description`` of a field's ``Field(...)`` becomes the field's
  docstring, and its default the field's value.

The async client needs nothing: Griffe labels every coroutine function ``async``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from typing import Any

import griffe

_TYPE_CHECKING_TESTS = frozenset({"TYPE_CHECKING", "typing.TYPE_CHECKING"})
_DEPRECATION_DECORATORS = frozenset(
    {
        "permit.utils.deprecation.deprecated",
        "typing_extensions.deprecated",
        "warnings.deprecated",
    }
)
_PYDANTIC_FIELDS = frozenset({"pydantic.Field", "pydantic.v1.Field"})
_CONTEXT_MANAGER_DECORATORS = frozenset({"contextlib.contextmanager"})


def _in_type_checking_branch(node: ast.AST) -> bool:
    """Whether ``node`` is a statement of the ``if`` branch of an ``if TYPE_CHECKING:``."""
    parent = getattr(node, "parent", None)
    return (
        isinstance(parent, ast.If)
        and node in parent.body
        and ast.unparse(parent.test) in _TYPE_CHECKING_TESTS
    )


def _evaluate_message(argument: ast.expr, module_path: str) -> str:
    """Evaluate a deprecation decorator's message argument.

    Args:
        argument: The argument: a string literal, or a call with literal arguments to a
            function of the decorated object's module.
        module_path: The path of that module, imported to call the function.

    Returns:
        The message.

    Raises:
        ValueError: If the argument has another shape, or does not evaluate to a string.
    """
    message: object = None
    if isinstance(argument, ast.Constant):
        message = argument.value
    elif (
        isinstance(argument, ast.Call)
        and isinstance(argument.func, ast.Name)
        and not argument.keywords
    ):
        function = getattr(importlib.import_module(module_path), argument.func.id)
        message = function(*(ast.literal_eval(arg) for arg in argument.args))
    if not isinstance(message, str):
        msg = (
            f"Cannot read the deprecation message {ast.unparse(argument)!r} in {module_path}: "
            "pass a string literal, or a call with literal arguments to a function of the "
            "same module, or teach scripts/docs_griffe_extension.py the new form."
        )
        raise ValueError(msg)  # noqa: TRY004 - a wrong value in the source, not a wrong type
    return message


def _mark_deprecated(
    obj: griffe.Object, message: str, parser: griffe.DocstringStyle | griffe.Parser | None
) -> None:
    """Label ``obj`` deprecated and end its docstring with ``message``, as a warning box.

    Args:
        obj: The deprecated function or class.
        message: The deprecation message.
        parser: The docstring parser for a docstring this creates, the one the loader uses:
            it is what turns the warning section into a box.
    """
    obj.deprecated = message
    obj.labels.add("deprecated")
    notice = f"Warning: Deprecated\n    {message}"
    if obj.docstring is None:
        obj.docstring = griffe.Docstring(notice, parent=obj, parser=parser)
    else:
        obj.docstring.value = f"{obj.docstring.value}\n\n{notice}"


def _show_as_context_manager(func: griffe.Function) -> None:
    """Show a ``@contextmanager`` generator function's return type as a context manager.

    Args:
        func: The function, annotated ``-> Generator[Y, ...]`` or ``-> Iterator[Y]``. Its
            return type becomes ``AbstractContextManager[Y]``.

    Raises:
        ValueError: If the return annotation does not name what the generator yields.
    """
    returns = func.returns
    if not isinstance(returns, griffe.ExprSubscript):
        msg = (
            f"Cannot read what {func.path} yields from its return annotation {returns!s}: "
            "annotate it as Generator[...] or Iterator[...]."
        )
        raise ValueError(msg)  # noqa: TRY004 - a wrong annotation in the source, not a wrong type
    if func.docstring is not None:
        # Parse the docstring now, while the annotation still names the generator: an item of
        # its Yields section that has no type takes the yielded type from it. The rendered page
        # reads these parsed sections.
        func.docstring.parsed  # noqa: B018 - cached on first access
    yielded = returns.slice
    if isinstance(yielded, griffe.ExprTuple):
        yielded = yielded.elements[0]
    func.returns = griffe.ExprSubscript(
        griffe.ExprName("AbstractContextManager", parent="contextlib"), yielded
    )


def _document_pydantic_field(
    attr: griffe.Attribute, field: griffe.ExprCall, call: ast.Call
) -> None:
    """Document a pydantic ``name: type = Field(...)`` as the field it declares.

    The ``description`` becomes the docstring, and the default becomes the value, so the
    page shows ``name: type = default`` rather than the whole ``Field(...)`` call.

    Args:
        attr: The field.
        field: The ``Field(...)`` call, as Griffe reads it.
        call: The same call, as parsed, for the literal value of its description.
    """
    for keyword in call.keywords:
        if keyword.arg == "description" and attr.docstring is None:
            # No parser: the description is prose, not a Google-style docstring.
            attr.docstring = griffe.Docstring(
                inspect.cleandoc(ast.literal_eval(keyword.value)),
                lineno=call.lineno,
                endlineno=call.end_lineno,
                parent=attr,
            )
    keywords = {
        arg.name: arg.value for arg in field.arguments if isinstance(arg, griffe.ExprKeyword)
    }
    positional = [arg for arg in field.arguments if not isinstance(arg, griffe.ExprKeyword)]
    if "default" in keywords:
        attr.value = keywords["default"]
    elif "default_factory" in keywords:
        factory = keywords["default_factory"]
        attr.value = griffe.ExprCall(factory, []) if isinstance(factory, griffe.Expr) else None
    elif positional and str(positional[0]) != "...":
        attr.value = positional[0]
    else:
        attr.value = None


class PermitDocs(griffe.Extension):
    """Make the API reference show the SDK as type checkers see it."""

    def __init__(self) -> None:
        super().__init__()
        # Full path of a name -> what the `if TYPE_CHECKING:` branch binds it to.
        self._checked_bindings: dict[str, griffe.Alias | griffe.Attribute] = {}
        # Full path of a stub class -> full path of the async class it is generated from.
        self._async_origins: dict[str, str] = {}

    def on_alias_instance(
        self, *, alias: griffe.Alias, node: ast.AST | griffe.ObjectNode, **kwargs: Any
    ) -> None:
        """Record an import in an ``if TYPE_CHECKING:`` branch."""
        if isinstance(node, ast.AST) and _in_type_checking_branch(node):
            self._checked_bindings[alias.path] = alias

    def on_attribute_instance(
        self, *, node: ast.AST | griffe.ObjectNode, attr: griffe.Attribute, **kwargs: Any
    ) -> None:
        """Record an assignment in an ``if TYPE_CHECKING:`` branch; document pydantic fields."""
        if not isinstance(node, ast.AST):
            return
        if _in_type_checking_branch(node):
            if isinstance(attr.value, griffe.ExprName):
                # `Name = OtherName` makes Name another name for the class OtherName.
                self._checked_bindings[attr.path] = griffe.Alias(
                    attr.name,
                    attr.value.canonical_path,
                    lineno=attr.lineno,
                    endlineno=attr.endlineno,
                )
            else:
                self._checked_bindings[attr.path] = attr
        call = getattr(node, "value", None)
        field = attr.value
        if (
            isinstance(call, ast.Call)
            and isinstance(field, griffe.ExprCall)
            and field.function.canonical_path in _PYDANTIC_FIELDS
        ):
            _document_pydantic_field(attr, field, call)

    def on_function_instance(
        self,
        *,
        node: ast.AST | griffe.ObjectNode,
        func: griffe.Function,
        agent: griffe.Visitor | griffe.Inspector,
        **kwargs: Any,
    ) -> None:
        """Label a function its decorator marks as deprecated; show a context manager's type."""
        self._read_deprecation(node, func, agent)
        if any(
            decorator.callable_path in _CONTEXT_MANAGER_DECORATORS for decorator in func.decorators
        ):
            _show_as_context_manager(func)

    def on_class_instance(
        self,
        *,
        node: ast.AST | griffe.ObjectNode,
        cls: griffe.Class,
        agent: griffe.Visitor | griffe.Inspector,
        **kwargs: Any,
    ) -> None:
        """Label a class its decorator marks as deprecated."""
        self._read_deprecation(node, cls, agent)

    def on_module_members(self, *, mod: griffe.Module, **kwargs: Any) -> None:
        """Put back what the ``if TYPE_CHECKING:`` branch binds where the runtime rebinds it.

        Only a runtime class or assignment is replaced. A runtime import, such as the
        pydantic imports every model module makes per pydantic major, stays.
        """
        for path, checked in self._checked_bindings.items():
            parent_path, name = path.rsplit(".", 1)
            runtime = mod.members.get(name) if parent_path == mod.path else None
            if runtime is None or runtime is checked or runtime.is_alias:
                continue
            if isinstance(runtime, griffe.Class) and isinstance(checked, griffe.Alias):
                base = runtime.bases[0] if runtime.bases else None
                if isinstance(base, griffe.Expr):
                    self._async_origins[checked.target_path] = base.canonical_path
            mod.set_member(name, checked)

    def on_package(self, *, pkg: griffe.Module, loader: griffe.GriffeLoader, **kwargs: Any) -> None:
        """Give each stub method the deprecation of the async method it is generated from."""
        collection = pkg.modules_collection
        for stub_path, async_path in self._async_origins.items():
            stub_class = collection.get_member(stub_path)
            async_class = collection.get_member(async_path)
            for name, method in stub_class.members.items():
                origin = async_class.all_members.get(name)
                if origin is None or method.is_alias:
                    continue
                message = origin.final_target.deprecated if origin.is_alias else origin.deprecated
                if isinstance(message, str):
                    _mark_deprecated(method, message, loader.docstring_parser)

    @staticmethod
    def _read_deprecation(
        node: ast.AST | griffe.ObjectNode,
        obj: griffe.Function | griffe.Class,
        agent: griffe.Visitor | griffe.Inspector,
    ) -> None:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        for decorator, decorator_node in zip(obj.decorators, node.decorator_list, strict=True):
            if (
                decorator.callable_path in _DEPRECATION_DECORATORS
                and isinstance(decorator_node, ast.Call)
                and decorator_node.args
            ):
                message = _evaluate_message(decorator_node.args[0], obj.module.path)
                _mark_deprecated(obj, message, agent.docstring_parser)
