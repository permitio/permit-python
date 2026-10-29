![Python.png](https://raw.githubusercontent.com/permitio/permit-python/main/imgs/Python.png)
# Permit.io Python SDK

Python SDK for interacting with the Permit.io full-stack permissions platform.

## Installation

```py
pip install permit
```

## Documentation

[Read the documentation at Permit.io website](https://docs.permit.io/sdk/python/quickstart-python)

## Upgrading from 2.x

permit 3.0.0 requires Python 3.10 or later and raises the minimum versions of its dependencies.
The [migration guide](https://github.com/permitio/permit-python/blob/main/MIGRATION.md) lists
every breaking change, who it affects and what to change. To have an AI agent such as Claude Code
do the upgrade, use the
[permit-python-3-migration skill](https://github.com/permitio/permit-python/tree/main/skills/permit-python-3-migration).

## Type checking

The package ships a `py.typed` marker (PEP 561), so mypy, pyright and IDEs check your
calls into the SDK against its type annotations. No pydantic mypy plugin is needed.

- The SDK's models are pydantic v1 models under both pydantic majors (with pydantic 2
  installed they come from `pydantic.v1`), and type checkers see them that way: use
  `.dict()` and `.json()` on them, not `.model_dump()`.
- Methods that take a model also accept an equivalent dict, such as
  `permit.api.users.create({"key": "user"})`, and bulk methods take a list of either.
  The dict is still validated at runtime.
- Model constructors are typed by their fields, so a nested model field takes a model
  instance, not a dict:
  `ResourceCreate(key="doc", name="Doc", actions={"read": ActionBlockEditable()})`.
  pydantic accepts a nested dict there at runtime, but a type checker rejects it. To
  pass plain dicts, give the whole payload to the API method as a dict instead.
- The blocking client, `permit.sync.Permit`, is typed as blocking:
  `permit.api.users.get("user")` returns a `UserRead`, not a coroutine.

## Logging

The SDK logs with [loguru](https://github.com/Delgan/loguru) and logs nothing unless you
enable it in the `log` option:

```py
permit = Permit(token="<YOUR_API_KEY>", log={"enable": True, "level": "debug"})
```

- The SDK adds no loguru sink of its own. Its records go to the sinks your application has
  added, or to loguru's default stderr sink, in the format of those sinks.
- `"enable": False` (the default) calls loguru's `logger.disable("permit")`. `"enable": True`
  undoes that call, with `logger.enable("permit")`, only if an earlier client made it.
  Otherwise a `logger.disable()` your application made for `permit` or one of its modules
  still applies. When it does undo it, loguru's `logger.enable("permit")` also undoes your
  application's own `logger.disable("permit")`, every `logger.disable()` your application
  made for a `permit.*` module, before or since, and, for the SDK's records, an
  application-wide `logger.disable("")`. Make those calls after creating the clients if
  they must hold.
- `level` (default `"info"`) is the lowest severity the SDK logs. Its records below it never
  reach a sink. Your application's own records are not affected. The SDK logs its HTTP
  requests and the PDP's responses at `"debug"`. With `"enable": True`, for a level name
  loguru does not know, the SDK logs a warning that names it and uses `"info"`.
- `label` (default `"Permit"`) is put in square brackets before every message the SDK logs.
- `json` is not applied. For JSON output, give your application a serialized sink in place
  of loguru's default one: `logger.remove()`, then `logger.add(sys.stderr, serialize=True)`.
  Added next to the default sink, it prints every record a second time.
- loguru's logger is process-wide, so these settings are too: the client created last
  decides whether the SDK logs, and the last one created with `"enable": True` decides the
  level and the label, for every client in the process. `wait_for_sync()` builds a new
  client of the same class, but keeps the process's log settings as they are.
- The SDK replaces the API key of every client in the process, as given and in lower case,
  with `[REDACTED]` in:
  - the messages it logs;
  - the messages of the exceptions it raises, and the error bodies in them
    (`PermitApiError.details`);
  - the aiohttp response or error those exceptions carry (`original_error`, `response`,
    the cause), and the exceptions chained under that error that aiohttp and the
    libraries it uses raised during the request: the request headers they keep, the
    request headers of the redirect responses in their `history`, and each error's
    arguments and attributes that are strings or bytes (such as its message), the
    response headers it keeps, and the URL of an invalid-URL error (`InvalidURL.url`,
    which then becomes a string).

  The SDK never changes an exception it did not raise during the request, such as one
  your application was handling when it called the SDK, which aiohttp keeps in its
  error's chain. If the key cannot be removed from the aiohttp error, the SDK attaches a
  plain `aiohttp.ClientError` that says so in its place, as `original_error` and as the
  cause.

  It does not replace the key elsewhere: not in values that are neither text nor a URL,
  such as a parsed HTTP message; not in request URLs (`PermitApiError.request_url`, the
  `url` and `real_url` of a response or its `request_info`, the `url=` part of an aiohttp
  error's text); not in the headers or raw body of a response itself
  (`PermitApiError.response.headers`, a redirect response's `Location`,
  `await PermitApiError.response.text()`); and not in the values a traceback shows for
  each frame (loguru's `diagnose=True`, error trackers that record local variables), where
  the key is in the client's options and its request headers. A key shorter than 12
  characters is not replaced. The client's start-up line shows `api_url` and `pdp` without
  any user name or password in them.
- `level` also takes a loguru severity number, such as `10` for DEBUG. An unknown name is
  warned about once per process.

## Deprecations

A future major release, permit 4.0, will remove the following. They still work in 3.x, and
each one issues a `DeprecationWarning` that says what to do instead.

- **pydantic 1 support.** On pydantic 1, `import permit` warns once. Upgrade to pydantic 2.
  The SDK's models then come from `pydantic.v1`, so their methods stay the same, but
  invalid input raises `pydantic.v1.ValidationError` rather than `pydantic.ValidationError`.
  Catching `pydantic.v1.ValidationError` works under both majors. Until you upgrade, the
  warning filter `ignore:Support for pydantic 1:DeprecationWarning` silences the import warning.
- **The flat methods on `permit.api`**, such as `permit.api.get_user()`. Use the grouped
  APIs instead, such as `permit.api.users.get()`. Each flat method's warning names its
  replacement.

By default, Python shows these warnings only when the code that triggers them is in
`__main__`, such as the script you run. pytest shows them in its warnings summary. To see
them elsewhere, such as in a web app, run Python with `-W default::DeprecationWarning` or
set the environment variable `PYTHONWARNINGS=default::DeprecationWarning`.

## Contributing

See [CONTRIBUTING.md](https://github.com/permitio/permit-python/blob/main/CONTRIBUTING.md).
