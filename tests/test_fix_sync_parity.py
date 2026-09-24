"""Parity between the blocking client and the async client it mirrors.

permit.sync.Permit is assembled by hand: SyncPermitApiClient repeats every sub-API
property of PermitApiClient, SyncPDPApi inherits PermitPdpApiClient and replaces the
sub-APIs it converts, and permit.sync.Permit overrides each public coroutine of
permit.Permit. Anything added to the async side alone reaches the blocking client
missing or still async. These tests walk both clients' public surfaces through their
properties and compare them. They are pure reflection: no network, API key or PDP.

The walk descends through properties only. Public instance attributes are compared by
name, and by class when they hold an async API, but are not walked into. The async
checks see what SyncClass converts: coroutine functions, and wrappers that lead to one
through ``__wrapped__``. A plain function that returns a coroutine, or an async
generator, looks blocking to them, and SyncClass would not convert it either.

tests/test_typing_surface.py covers the other half: each blocking class converts every
method of the async class it subclasses.
"""

from typing import Any

import pytest

from permit import Permit as AsyncPermit
from permit import PermitConfig
from permit.sync import Permit as SyncPermit
from permit.utils.sync import SyncClass, iscoroutine_func

Surface = dict[str, Any]

# PermitApiClient has this many sub-API properties. The walk descends only through
# properties, so if it finds fewer it has stopped seeing them, and the parity checks
# pass without having looked. Lower it only when a sub-API is removed.
API_SUB_API_COUNT = 17


def offline_config() -> PermitConfig:
    return PermitConfig(token="permit_key_offline", pdp="http://localhost:7766")


def public_names(obj: object) -> set[str]:
    """Public attributes of ``obj``'s class, plus ``obj``'s own public instance attributes.

    A callable's ``__dict__`` is left out: a bound method exposes its function's, where
    decorators such as pydantic's ``validate_arguments`` keep helpers like ``raw_function``.
    """
    names = set(dir(type(obj)))
    if not callable(obj):
        names |= set(getattr(obj, "__dict__", {}))
    return {name for name in names if not name.startswith("_")}


def is_property(obj: object, name: str) -> bool:
    return isinstance(getattr(type(obj), name, None), property)


def property_names(obj: object) -> set[str]:
    return {name for name in public_names(obj) if is_property(obj, name)}


def is_one_of(obj: object, candidates: tuple[object, ...]) -> bool:
    return any(obj is candidate for candidate in candidates)


def public_surface(obj: object, prefix: str = "", ancestors: tuple[object, ...] = ()) -> Surface:
    """Every public attribute reachable from ``obj`` through properties, keyed by dotted path.

    A property that leads back to ``obj`` or one of its ancestors is recorded but not
    walked again, so a back-reference cannot recurse forever.
    """
    ancestors = (*ancestors, obj)
    surface: Surface = {}
    for name in sorted(public_names(obj)):
        path = prefix + name
        surface[path] = getattr(obj, name)
        if is_property(obj, name) and not is_one_of(surface[path], ancestors):
            surface.update(public_surface(surface[path], f"{path}.", ancestors))
    return surface


def is_async_api(obj: object) -> bool:
    """Whether ``obj`` has public methods that return awaitables."""
    values = (getattr(obj, name) for name in public_names(obj))
    return any(callable(value) and iscoroutine_func(value) for value in values)


@pytest.fixture(scope="module")
def async_client() -> AsyncPermit:
    return AsyncPermit(offline_config())


@pytest.fixture(scope="module")
def async_surface(async_client: AsyncPermit) -> Surface:
    return public_surface(async_client)


@pytest.fixture(scope="module")
def sync_surface() -> Surface:
    return public_surface(SyncPermit(offline_config()))


def test_the_walk_reaches_every_sub_api(async_client: AsyncPermit, async_surface: Surface):
    """The other tests compare what the walk finds, so it must find the sub-APIs.

    Only the async walk is checked here: test_sync_client_has_every_async_attribute
    requires the sync walk to find every path this one does. A property whose value has
    nothing public, or leads back to an object the walk is already inside, has nothing
    below it to find.
    """
    api_sub_apis = property_names(async_client.api)
    assert len(api_sub_apis) >= API_SUB_API_COUNT, f"permit.Permit().api properties: {sorted(api_sub_apis)}"

    for prefix, ancestors in (
        ("", (async_client,)),
        ("api.", (async_client, async_client.api)),
        ("pdp_api.", (async_client, async_client.pdp_api)),
    ):
        obj = ancestors[-1]
        unwalked = sorted(
            prefix + name
            for name in property_names(obj)
            if public_names(getattr(obj, name))
            and not is_one_of(getattr(obj, name), ancestors)
            and not any(path.startswith(f"{prefix}{name}.") for path in async_surface)
        )
        assert not unwalked, f"the walk did not descend into {unwalked}"


def test_sync_client_has_every_async_attribute(async_surface: Surface, sync_surface: Surface):
    missing = sorted(set(async_surface) - set(sync_surface))

    assert not missing, f"on permit.Permit but not on permit.sync.Permit: {missing}"


def test_sync_client_keeps_every_async_method_callable(async_surface: Surface, sync_surface: Surface):
    not_callable = sorted(
        path
        for path, value in async_surface.items()
        if callable(value) and path in sync_surface and not callable(sync_surface[path])
    )

    assert not not_callable, f"callable on permit.Permit but not on permit.sync.Permit: {not_callable}"


def test_nothing_reachable_from_the_sync_client_is_async(sync_surface: Surface):
    still_async = sorted(path for path, value in sync_surface.items() if callable(value) and iscoroutine_func(value))

    assert not still_async, f"permit.sync.Permit still returns awaitables from: {still_async}"


def test_sync_client_uses_a_sync_class_for_every_async_api(async_surface: Surface, sync_surface: Surface):
    not_sync_class = sorted(
        f"{path} is {type(sync_surface[path]).__qualname__}"
        for path, value in async_surface.items()
        if is_async_api(value) and path in sync_surface and not isinstance(type(sync_surface[path]), SyncClass)
    )

    assert not not_sync_class, f"permit.sync.Permit exposes API objects not built with SyncClass: {not_sync_class}"
