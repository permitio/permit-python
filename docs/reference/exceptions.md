# Exceptions

The SDK's exceptions are `PermitError` subclasses. A call to the Permit REST API that the API
answers with an error status raises a `PermitApiError` or one of its subclasses. An
authorization query that cannot reach the PDP, or that the PDP answers with an error status,
raises a `PermitConnectionError`.

::: permit.exceptions.PermitError

::: permit.exceptions.PermitApiError

::: permit.exceptions.PermitApiDetailedError

::: permit.exceptions.PermitValidationError

::: permit.exceptions.PermitAlreadyExistsError

::: permit.exceptions.PermitNotFoundError

::: permit.exceptions.PermitConnectionError

::: permit.exceptions.PermitContextError

::: permit.exceptions.PermitContextChangeError

::: permit.exceptions.PermitException
