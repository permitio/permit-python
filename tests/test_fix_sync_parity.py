"""Parity between the blocking client and the async client it mirrors.

permit.sync.Permit is assembled by hand: SyncPermitApiClient repeats every sub-API
property of PermitApiClient, SyncPDPApi inherits PermitPdpApiClient and replaces the
sub-APIs it converts, and permit.sync.Permit overrides each public coroutine of
permit.Permit. Anything added to the async side alone reaches the blocking client
missing or still async. These tests walk both clients' public surfaces through their
properties and compare them. They are pure reflection: no network, API key or PDP.

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
    return {name for name in dir(type(obj)) if not name.startswith("_")}


def is_property(obj: object, name: str) -> bool:
    return isinstance(getattr(type(obj), name, None), property)


def property_names(obj: object) -> set[str]:
    return {name for name in public_names(obj) if is_property(obj, name)}


def public_surface(obj: object, prefix: str = "") -> Surface:
    """Every public attribute reachable from ``obj`` through properties, keyed by dotted path."""
    surface: Surface = {}
    for name in sorted(public_names(obj)):
        path = prefix + name
        surface[path] = getattr(obj, name)
        if is_property(obj, name):
            surface.update(public_surface(surface[path], f"{path}."))
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
    requires the sync walk to find every path this one does.
    """
    api_sub_apis = property_names(async_client.api)
    assert len(api_sub_apis) >= API_SUB_API_COUNT, f"permit.Permit().api properties: {sorted(api_sub_apis)}"

    for prefix, obj in (("", async_client), ("api.", async_client.api), ("pdp_api.", async_client.pdp_api)):
        unwalked = sorted(
            prefix + name
            for name in property_names(obj)
            if not any(path.startswith(f"{prefix}{name}.") for path in async_surface)
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


def test_sync_client_uses_a_blocking_class_for_every_async_api(async_surface: Surface, sync_surface: Surface):
    not_blocking = sorted(
        f"{path} is {type(sync_surface[path]).__qualname__}"
        for path, value in async_surface.items()
        if is_async_api(value) and path in sync_surface and not isinstance(type(sync_surface[path]), SyncClass)
    )

    assert not not_blocking, f"permit.sync.Permit exposes async API classes: {not_blocking}"
