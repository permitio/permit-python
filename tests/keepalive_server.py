"""A local HTTP/1.1 server that keeps its connections open and counts them.

pytest-httpserver answers in HTTP/1.0 and closes each connection after its response, so it
cannot show whether a client reuses connections. This server keeps every connection open
for the next request, as the Permit API and the PDP do, and counts the connections it
accepted and those the client closed.
"""

import asyncio
import json
import threading
from typing import NamedTuple

# How long the server's own startup and shutdown may take before a test fails.
_SERVER_TIMEOUT_SECONDS = 5.0


class ServedRequest(NamedTuple):
    """A request the server answered: its method, path and headers (names as sent)."""

    method: str
    path: str
    headers: dict[str, str]


class _Response(NamedTuple):
    body: bytes
    headers: dict[str, str]
    delay: float


class KeepAliveServer:
    """Answers JSON on 127.0.0.1, from an event loop in a thread of its own.

    Every path answers ``{"allow": true}`` unless ``respond()`` set another answer for it.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="keepalive-server", daemon=True
        )
        self._changed = threading.Condition()
        self._opened = 0
        self._closed = 0
        self._responses: dict[str, _Response] = {}
        self._server: asyncio.Server | None = None
        self.requests: list[ServedRequest] = []

    def start(self) -> None:
        self._thread.start()
        self._server = asyncio.run_coroutine_threadsafe(
            asyncio.start_server(self._serve, "127.0.0.1", 0), self._loop
        ).result(_SERVER_TIMEOUT_SECONDS)

    def stop(self) -> None:
        asyncio.run_coroutine_threadsafe(self._shut_down(), self._loop).result(
            _SERVER_TIMEOUT_SECONDS
        )
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(_SERVER_TIMEOUT_SECONDS)
        self._loop.close()

    @property
    def url(self) -> str:
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

    def respond(
        self,
        path: str,
        body: object,
        *,
        headers: dict[str, str] | None = None,
        delay: float = 0.0,
    ) -> None:
        """Answer requests to ``path`` with ``body`` as JSON, after ``delay`` seconds."""
        self._responses[path] = _Response(json.dumps(body).encode(), headers or {}, delay)

    def wait_until_closed(self, count: int, timeout: float = _SERVER_TIMEOUT_SECONDS) -> int:
        """Wait until ``count`` connections were closed, and return how many were.

        It returns once they are, or once ``timeout`` seconds have passed.
        """
        with self._changed:
            self._changed.wait_for(lambda: self._closed >= count, timeout)
            return self._closed

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        with self._changed:
            self._opened += 1
        try:
            while await self._answer_one(reader, writer):
                pass
        except ConnectionError:
            pass
        finally:
            writer.close()
            with self._changed:
                self._closed += 1
                self._changed.notify_all()

    async def _answer_one(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
        """Answer the connection's next request; False once the client closed it."""
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except asyncio.IncompleteReadError:
            return False
        request_line, *header_lines = head.decode("latin-1").rstrip("\r\n").split("\r\n")
        method, target, _ = request_line.split(" ")
        headers = dict(line.split(": ", 1) for line in header_lines)
        length = next((v for k, v in headers.items() if k.lower() == "content-length"), "0")
        await reader.readexactly(int(length))
        path = target.split("?", 1)[0]
        self.requests.append(ServedRequest(method, path, headers))

        response = self._responses.get(path, _Response(b'{"allow": true}', {}, 0.0))
        if response.delay:
            await asyncio.sleep(response.delay)
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
        handlers = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        for handler in handlers:
            handler.cancel()
        await asyncio.gather(*handlers, return_exceptions=True)
        await self._server.wait_closed()
