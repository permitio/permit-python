from typing import TYPE_CHECKING, Any, Dict, List, Sequence, TypeVar, Union

if TYPE_CHECKING:
    _Model = TypeVar("_Model")

    ModelInput = Union[_Model, Dict[str, Any]]
    """Annotation for an SDK method parameter that takes a model or an equivalent dict.

    Methods decorated with ``validate_arguments`` validate a dict argument into the
    annotated model, so ``create({"key": "user"})`` works. Type checkers only accept
    that call if the annotation also allows a dict.
    """

    ModelListInput = Sequence[Union[_Model, Dict[str, Any]]]
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

        def __class_getitem__(cls, model: type) -> Any:
            return List[model]
