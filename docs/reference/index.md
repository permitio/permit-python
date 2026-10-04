# Reference

Every public class and method of permit, generated from its docstrings and type annotations.
For guides and concepts, see the [Python SDK docs on docs.permit.io](https://docs.permit.io/sdk/python/quickstart-python/);
for the endpoints behind `permit.api`, the [REST API reference](https://api.permit.io/scalar).

- [Async client](permit.md) and [blocking client](sync.md): `permit.Permit` and
  `permit.sync.Permit`, the authorization checks, and the `api`, `pdp_api` and `elements`
  attributes. [Async or blocking client](../clients.md) says which to choose.
- [Configuration](config.md): `PermitConfig`, the options a client takes.
- [Exceptions](exceptions.md): what the SDK raises.
- [Enforcement types](enforcement.md): the user and resource types `check()` and the other
  authorization queries take, and the results they return.
- [REST API](api/index.md): `permit.api`, one page per API.
- [PDP API](pdp-api.md) and [Elements](elements.md): `permit.pdp_api` and `permit.elements`.
- [Models](models.md): the models the methods take and return.

## Reading the signatures

- A method with the `async` label is a coroutine function: `await` its call. The blocking
  client's methods have the same parameters and return the result directly.
- `ModelInput[X]` is a model `X` or a dict with its fields, such as
  `{"key": "user"}` for a `UserCreate`. The dict is validated into `X` at runtime.
  `ModelListInput[X]` is a sequence of either.
- A method with the `deprecated` label still works and issues a `DeprecationWarning`. Its
  docstring ends with what to use instead and the release that removes it.
