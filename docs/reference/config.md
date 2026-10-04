# Configuration

A client takes its configuration as keyword arguments, `Permit(token="<YOUR_API_KEY>",
pdp="http://localhost:7766")`, or as a `PermitConfig`, `Permit(PermitConfig(token=...))`.
The keyword arguments are the fields of `PermitConfig`. For where to run the PDP and which
API key to use, see the [Python quickstart on docs.permit.io](https://docs.permit.io/sdk/python/quickstart-python/).

::: permit.config.PermitConfig

::: permit.config.LoggerConfig

::: permit.config.MultiTenancyConfig

::: permit.api.context.ApiContext

::: permit.api.context.ApiKeyAccessLevel

::: permit.api.context.ApiContextLevel
