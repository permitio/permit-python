"""End-to-end tests of the blocking client, called from one thread and from many.

The blocking client runs every call on an event loop in a background thread of its own, so
the calls of many threads that share one client all go through that one loop. Each thread
creates a user of its own, reads it back and deletes it; the main thread reads every
thread's result, so a call that raises in a thread fails the test.
"""

import functools
import threading
from collections.abc import Callable
from concurrent.futures import Future
from contextlib import ExitStack
from typing import TypeVar

import pytest

from permit import PermitConfig, UserCreate, UserRead
from permit.exceptions import PermitNotFoundError
from permit.sync import Permit
from tests.utils import delete_quietly_blocking, unique_key

pytestmark = pytest.mark.e2e

THREADS = 10
# How long to wait for a thread's result, or for a client's close(), which waits for the
# calls in flight. Long enough for the rate-limit retries of conftest.py, which can hold one
# call for about two minutes; short enough that a call that never returns fails the test.
TIMEOUT_S = 300

T = TypeVar("T")


def create_read_delete(permit: Permit, user_key: str) -> UserRead:
    """Create a user, read it back and delete it. It is deleted at the end whatever happens."""
    with ExitStack() as teardown:
        teardown.callback(
            delete_quietly_blocking,
            functools.partial(permit.api.users.delete, user_key),
            f"user '{user_key}'",
        )
        permit.api.users.create(UserCreate(key=user_key, email=f"{user_key}@example.com"))
        user = permit.api.users.get(user_key)
        permit.api.users.delete(user_key)
        with pytest.raises(PermitNotFoundError):
            permit.api.users.get(user_key)
    return user


def run_in_threads(calls: list[Callable[[], T]]) -> list[T]:
    """Run each call on a thread of its own, all at once, and return what each returned.

    Every result is read, with a time limit, so a call that raises in its thread raises
    here, and one that never returns fails the test. The threads are daemons, unlike a
    ThreadPoolExecutor's, which the interpreter waits for at exit, so a stuck one cannot
    hold up the end of the test session either.
    """
    futures: list[Future[T]] = [Future() for _ in calls]

    def run(work: Callable[[], T], future: Future[T]) -> None:
        try:
            future.set_result(work())
        # BaseException: a pytest failure, such as pytest.raises() not raising, is not an Exception.
        except BaseException as error:
            future.set_exception(error)

    for work, future in zip(calls, futures, strict=True):
        threading.Thread(target=run, args=(work, future), daemon=True).start()
    return [future.result(timeout=TIMEOUT_S) for future in futures]


def close_within(client: Permit) -> None:
    """Close ``client``, failing instead of waiting forever for a call that never returns."""
    closing = threading.Thread(target=client.close, daemon=True)
    closing.start()
    closing.join(TIMEOUT_S)
    assert not closing.is_alive(), "close() did not return: a call on the client is stuck"


def test_sync_client(permit_config: PermitConfig) -> None:
    user_key = unique_key("sync-client")

    with Permit(permit_config) as permit:
        user = create_read_delete(permit, user_key)

    assert type(user) is UserRead
    assert (user.key, user.email) == (user_key, f"{user_key}@example.com")


def test_threads_sharing_one_sync_client(permit_config: PermitConfig) -> None:
    """Every thread's calls go through the one background loop of the client they share."""
    keys = [unique_key("sync-shared") for _ in range(THREADS)]

    with ExitStack() as clients:
        permit = Permit(permit_config)
        clients.callback(close_within, permit)
        users = run_in_threads([functools.partial(create_read_delete, permit, key) for key in keys])

    assert [type(user) for user in users] == [UserRead] * THREADS
    assert [user.key for user in users] == keys


def test_threads_each_with_a_sync_client_of_their_own(permit_config: PermitConfig) -> None:
    keys = [unique_key("sync-own") for _ in range(THREADS)]

    with ExitStack() as clients:
        calls: list[Callable[[], UserRead]] = []
        for key in keys:
            permit = Permit(permit_config)
            clients.callback(close_within, permit)
            calls.append(functools.partial(create_read_delete, permit, key))
        users = run_in_threads(calls)

    assert [type(user) for user in users] == [UserRead] * THREADS
    assert [user.key for user in users] == keys
