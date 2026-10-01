"""A keep-alive HTTP/1.1 server that counts the TCP connections its clients open.

pytest-httpserver's server closes the connection after every response, so it cannot show
whether a client reuses connections. This one keeps each connection open until the client
closes it, answers every request with the same JSON body, and counts the connections it
accepted, the ones still open and the requests it answered.
"""

import asyncio
import contextlib
import json
import threading
from types import TracebackType

from typing_extensions import Self

_HEADER_END = b"\r\n\r\n"


class ConnectionCountingServer:
    """A local HTTP/1.1 server on 127.0.0.1, running an event loop in a thread of its own.

    Args:
        body: The JSON value every response carries.
    """

    def __init__(self, body: object = None) -> None:
        self._body = json.dumps({"allow": True} if body is None else body).encode()
        self.response_delay = 0.0
        """Seconds to wait before answering each request."""
        self._changed = threading.Condition()
        self._accepted = 0
        self._open = 0
        self._requests = 0
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._server: asyncio.Server | None = None
        self._handlers: set[asyncio.Task[None]] = set()
        self._writers: set[asyncio.StreamWriter] = set()
        self.port = 0

    @property
    def url(self) -> str:
        """The server's base URL."""
        return f"http://127.0.0.1:{self.port}"

    @property
    def accepted(self) -> int:
        """How many TCP connections the server has accepted."""
        with self._changed:
            return self._accepted

    @property
    def open(self) -> int:
        """How many of those connections are still open."""
        with self._changed:
            return self._open

    @property
    def requests(self) -> int:
        """How many requests the server has read."""
        with self._changed:
            return self._requests

    def wait_for_open(self, count: int, timeout: float = 5.0) -> bool:
        """Wait until exactly `count` connections are open; False if `timeout` passes first."""
        with self._changed:
            return self._changed.wait_for(lambda: self._open == count, timeout)

    def wait_for_requests(self, count: int, timeout: float = 5.0) -> bool:
        """Wait until the server has read `count` requests; False if `timeout` passes first."""
        with self._changed:
            return self._changed.wait_for(lambda: self._requests >= count, timeout)

    def start(self) -> None:
        """Start serving on a free port."""
        self._thread.start()
        started = asyncio.run_coroutine_threadsafe(
            asyncio.start_server(self._serve, "127.0.0.1", 0), self._loop
        )
        self._server = started.result()
        self.port = self._server.sockets[0].getsockname()[1]

    def stop(self) -> None:
        """Close every connection, stop serving and stop the server's thread."""
        asyncio.run_coroutine_threadsafe(self._shut_down(), self._loop).result()
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()

    async def _shut_down(self) -> None:
        if self._server is not None:
            self._server.close()
        for writer in list(self._writers):
            writer.close()
        await asyncio.gather(*self._handlers, return_exceptions=True)
        if self._server is not None:
            await self._server.wait_closed()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        handler = asyncio.current_task()
        if handler is not None:
            self._handlers.add(handler)
        self._writers.add(writer)
        with self._changed:
            self._accepted += 1
            self._open += 1
            self._changed.notify_all()
        try:
            await self._answer_requests(reader, writer)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass  # The client closed the connection, which ends it.
        finally:
            self._writers.discard(writer)
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()
            with self._changed:
                self._open -= 1
                self._changed.notify_all()
            if handler is not None:
                self._handlers.discard(handler)

    async def _answer_requests(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        while True:
            head = await reader.readuntil(_HEADER_END)
            length = 0
            for line in head.decode("latin-1").split("\r\n")[1:]:
                name, _, value = line.partition(":")
                if name.strip().lower() == "content-length":
                    length = int(value)
            if length:
                await reader.readexactly(length)
            with self._changed:
                self._requests += 1
                self._changed.notify_all()
            if self.response_delay and await _closed_within(reader, self.response_delay):
                return
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                + f"Content-Length: {len(self._body)}\r\n\r\n".encode()
                + self._body
            )
            await writer.drain()


async def _closed_within(reader: asyncio.StreamReader, seconds: float) -> bool:
    """Whether the client closes the connection within `seconds`, sending nothing meanwhile.

    A client waiting for its response sends nothing, so this reads nothing it needs later.
    """
    try:
        return await asyncio.wait_for(reader.read(1), seconds) == b""
    except asyncio.TimeoutError:
        return False
