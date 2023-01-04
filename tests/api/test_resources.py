import pytest as pytest

from permit.api.client import PermitApiClient
from permit.openapi.models import ResourceCreate

pytest_plugins = ("pytest_asyncio",)


@pytest.mark.parametrize("resource_key", ["res1", "res2", "res3"])
async def test_create_resource(api_client: PermitApiClient, resource_key: str):
    create_resource = ResourceCreate(key=resource_key, name=resource_key, actions={})
    resource = await api_client.resources.create(create_resource)
    assert resource.key == create_resource.key
    assert resource.name == create_resource.name


@pytest.mark.parametrize("resource_key", ["res1", "res2", "res3"])
async def test_delete_resource(api_client: PermitApiClient, resource_key: str):
    create_resource = ResourceCreate(key=resource_key, name=resource_key, actions={})
    await api_client.resources.create(create_resource)
    res = await api_client.resources.delete(resource_key)
    assert res is None


@pytest.mark.parametrize("resource_key", ["res1", "res2", "res3"])
async def test_get_resource(api_client: PermitApiClient, resource_key: str):
    create_resource = ResourceCreate(key=resource_key, name=resource_key, actions={})
    resource = await api_client.resources.create(create_resource)
    res = await api_client.resources.delete(resource_key)
    assert res is None
