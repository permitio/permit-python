from typing import TYPE_CHECKING, Any, List, TypeVar  # noqa: UP035 - runtime annotation below

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TypeAlias

    _Model = TypeVar("_Model")

    ModelInput: TypeAlias = _Model | dict[str, Any]
    """Annotation for an SDK method parameter that takes a model or an equivalent dict.

    Methods decorated with ``validate_arguments`` validate a dict argument into the
    annotated model, so ``create({"key": "user"})`` works. Type checkers only accept
    that call if the annotation also allows a dict.
    """

    ModelListInput: TypeAlias = Sequence[_Model | dict[str, Any]]
    """Annotation for a bulk parameter that takes a list of models or equivalent dicts.

    A ``Sequence``, not a ``List``: ``List`` is invariant, so a type checker would
    reject a ``list[UserCreate]`` built before the call because it is not a
    ``list[UserCreate | dict]``.
    """
else:

    class ModelInput:
        """Runtime twin of the type-checking alias: ``ModelInput[X]`` is plain ``X``.

        The annotation ``validate_arguments`` reads must stay the bare model. Given
        ``Union[X, Dict[str, Any]]`` it would try each member in turn, so a dict
        that fails ``X``'s validation would still match ``Dict[str, Any]`` and reach
        the method unvalidated instead of raising ``ValidationError``.
        """

        def __class_getitem__(cls, model: type) -> type:
            return model

    class ModelListInput:
        """Runtime twin of the type-checking alias: ``ModelListInput[X]`` is ``List[X]``.

        ``validate_arguments`` must keep building a list of validated models, as it
        did before this annotation existed. Given ``Sequence[X]`` it would, for one,
        hand the method a tuple when the caller passed a tuple.
        """

        def __class_getitem__(cls, model: type) -> object:
            return List[model]  # noqa: UP006 - runtime annotation kept identical to 3.0.0
