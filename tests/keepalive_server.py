"""A local HTTP/1.1 server that keeps its connections open and counts them.

pytest-httpserver answers in HTTP/1.0 and closes each connection after its response, so it
cannot show whether a client reuses connections. This server keeps every connection open
until the client closes it, as the Permit API and the PDP do. It counts the connections it
accepted and those that were closed, and records the requests it read.
"""

import asyncio
import contextlib
import json
import threading
from types import TracebackType
from typing import NamedTuple

from typing_extensions import Self

# How long the server's own startup and shutdown, and a test's wait, may take.
_SERVER_TIMEOUT_SECONDS = 5.0
_HEADER_END = b"\r\n\r\n"


class ServedRequest(NamedTuple):
    """A request the server read: its method, path and headers (names as sent)."""

    method: str
    path: str
    headers: dict[str, str]


class _Response(NamedTuple):
    body: bytes
    headers: dict[str, str]
    delay: float


_ALLOW = _Response(b'{"allow": true}', {}, 0.0)


class KeepAliveServer:
    """Answers JSON on 127.0.0.1, from an event loop in a thread of its own.

    Every path answers ``{"allow": true}`` unless ``respond()`` set another answer for it.
    Use it as a context manager, or call ``start()`` and ``stop()``.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="keepalive-server", daemon=True
        )
        self._changed = threading.Condition()
        self._opened = 0
        self._closed = 0
        self._requests: list[ServedRequest] = []
        self._responses: dict[str, _Response] = {}
        self._server: asyncio.Server | None = None
        # Read and written on the server's loop only.
        self._handlers: set[asyncio.Task[None]] = set()
        self._writers: set[asyncio.StreamWriter] = set()

    def start(self) -> None:
        """Start serving on a free port."""
        self._thread.start()
        self._server = asyncio.run_coroutine_threadsafe(
            asyncio.start_server(self._serve, "127.0.0.1", 0), self._loop
        ).result(_SERVER_TIMEOUT_SECONDS)

    def stop(self) -> None:
        """Close every connection, stop serving and stop the server's thread."""
        asyncio.run_coroutine_threadsafe(self._shut_down(), self._loop).result(
            _SERVER_TIMEOUT_SECONDS
        )
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(_SERVER_TIMEOUT_SECONDS)
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

    @property
    def url(self) -> str:
        """The server's base URL."""
        assert self._server is not None
        host, port = self._server.sockets[0].getsockname()[:2]
        return f"http://{host}:{port}"

    @property
    def opened(self) -> int:
        """How many connections the server accepted."""
        with self._changed:
            return self._opened

    @property
    def closed(self) -> int:
        """How many of those connections were closed, by the client or by a failed write."""
        with self._changed:
            return self._closed

    @property
    def requests(self) -> list[ServedRequest]:
        """The requests the server read, in the order it read them."""
        with self._changed:
            return list(self._requests)

    def respond(
        self,
        path: str,
        body: object,
        *,
        headers: dict[str, str] | None = None,
        delay: float = 0.0,
    ) -> None:
        """Answer requests to ``path`` with ``body`` as JSON, after ``delay`` seconds.

        A client that closes the connection during the delay gets no answer, and the
        connection counts as closed then.
        """
        self._responses[path] = _Response(json.dumps(body).encode(), headers or {}, delay)

    def wait_until_closed(self, count: int, timeout: float = _SERVER_TIMEOUT_SECONDS) -> int:
        """Wait until ``count`` connections were closed, and return how many were.

        It returns once they are, or once ``timeout`` seconds have passed.
        """
        with self._changed:
            self._changed.wait_for(lambda: self._closed >= count, timeout)
            return self._closed

    def wait_for_requests(self, count: int, timeout: float = _SERVER_TIMEOUT_SECONDS) -> bool:
        """Wait until the server has read ``count`` requests; False if ``timeout`` passes first."""
        with self._changed:
            return self._changed.wait_for(lambda: len(self._requests) >= count, timeout)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        handler = asyncio.current_task()
        if handler is not None:
            self._handlers.add(handler)
        self._writers.add(writer)
        with self._changed:
            self._opened += 1
            self._changed.notify_all()
        try:
            while await self._answer_one(reader, writer):
                pass
        except (asyncio.IncompleteReadError, ConnectionError):
            pass  # The client closed the connection mid-request, which ends it.
        finally:
            self._writers.discard(writer)
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()
            with self._changed:
                self._closed += 1
                self._changed.notify_all()
            if handler is not None:
                self._handlers.discard(handler)

    async def _answer_one(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
        """Answer the connection's next request; False once the client closed it."""
        try:
            head = await reader.readuntil(_HEADER_END)
        except asyncio.IncompleteReadError:
            return False
        request_line, *header_lines = head.decode("latin-1").rstrip("\r\n").split("\r\n")
        method, target, _ = request_line.split(" ")
        headers = dict(line.split(": ", 1) for line in header_lines)
        length = next((v for k, v in headers.items() if k.lower() == "content-length"), "0")
        await reader.readexactly(int(length))
        path = target.split("?", 1)[0]
        with self._changed:
            self._requests.append(ServedRequest(method, path, headers))
            self._changed.notify_all()

        response = self._responses.get(path, _ALLOW)
        if response.delay and await _closed_within(reader, response.delay):
            return False
        extra_headers = "".join(f"{name}: {value}\r\n" for name, value in response.headers.items())
        writer.write(
            f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(response.body)}\r\n{extra_headers}\r\n".encode("latin-1")
            + response.body
        )
        await writer.drain()
        return True

    async def _shut_down(self) -> None:
        assert self._server is not None
        self._server.close()
        for writer in list(self._writers):
            writer.close()
        await asyncio.gather(*self._handlers, return_exceptions=True)
        await self._server.wait_closed()


async def _closed_within(reader: asyncio.StreamReader, seconds: float) -> bool:
    """Whether the client closes the connection within ``seconds``, sending nothing meanwhile.

    A client waiting for its response sends nothing, so this reads nothing it needs later.
    """
    try:
        return await asyncio.wait_for(reader.read(1), seconds) == b""
    except asyncio.TimeoutError:
        return False
