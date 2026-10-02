"""Benchmark: sequential check() calls against a local server that counts TCP connections.

Run it from the repository root, with the permit package to measure on the path:

    uv run --locked python -m tests.benchmark_connection_reuse --calls 200

For the async and the sync client, it makes that many check() calls one after the other,
and prints how many TCP connections they opened and how long each call took. A client that
keeps its HTTP session opens one connection; one that opens a session per call opens one
per call. The server answers on 127.0.0.1 without delay, so the times are the client's own
cost; against a remote PDP each new connection also pays a network round trip, and a TLS
handshake over https.
"""

import argparse
import asyncio
import statistics
import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

import permit
from permit import Permit
from permit.sync import Permit as SyncPermit
from tests.keepalive_server import KeepAliveServer
from tests.utils import offline_config

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

COLUMNS = ("client", "calls", "connections", "total ms", "mean ms", "p50 ms", "p95 ms")


def time_async_client(url: str, calls: int) -> list[float]:
    """The duration of each of `calls` sequential `await permit.check()` calls, in seconds."""

    async def main() -> list[float]:
        client = Permit(offline_config(url))
        durations = []
        for _ in range(calls):
            start = time.perf_counter()
            allowed = await client.check("user", "read", "document")
            durations.append(time.perf_counter() - start)
            assert allowed, "the server answers every check with allow: true"
        # The benchmark compares versions of permit, and the earlier ones have no close().
        close: Callable[[], Awaitable[None]] | None = getattr(client, "close", None)
        if close is not None:
            await close()
        return durations

    return asyncio.run(main())


def time_sync_client(url: str, calls: int) -> list[float]:
    """The duration of each of `calls` sequential blocking `permit.check()` calls, in seconds."""
    client = SyncPermit(offline_config(url))
    durations = []
    for _ in range(calls):
        start = time.perf_counter()
        allowed = client.check("user", "read", "document")
        durations.append(time.perf_counter() - start)
        assert allowed, "the server answers every check with allow: true"
    # The benchmark compares versions of permit, and the earlier ones have no close().
    close: Callable[[], None] | None = getattr(client, "close", None)
    if close is not None:
        close()
    return durations


def row(client: str, connections: int, durations: list[float]) -> tuple[str, ...]:
    """One line of the report, with the times in milliseconds."""
    milliseconds = [duration * 1000 for duration in durations]
    p95 = statistics.quantiles(milliseconds, n=20)[18]
    return (
        client,
        str(len(durations)),
        str(connections),
        f"{sum(milliseconds):.1f}",
        f"{statistics.fmean(milliseconds):.3f}",
        f"{statistics.median(milliseconds):.3f}",
        f"{p95:.3f}",
    )


def main() -> None:
    """Measure both clients and print the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--calls", type=int, default=200, help="check() calls per client")
    args = parser.parse_args()
    if args.calls < 2:
        parser.error("--calls must be at least 2")

    # Only the report goes to the terminal, not the SDK's debug records.
    logger.disable("permit")
    rows: list[tuple[str, ...]] = [COLUMNS]
    for name, measure in (("async", time_async_client), ("sync", time_sync_client)):
        with KeepAliveServer() as server:
            durations = measure(server.url, args.calls)
            rows.append(row(name, server.opened, durations))

    print(f"permit from {Path(permit.__file__).parent}")
    widths = [max(len(line[column]) for line in rows) for column in range(len(COLUMNS))]
    for line in rows:
        print("  ".join(cell.rjust(width) for cell, width in zip(line, widths, strict=True)))


if __name__ == "__main__":
    main()
