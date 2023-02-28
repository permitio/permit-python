import pytest
from pydantic import EmailStr

from permit.api.client import PermitApiClient
from permit.exceptions.base import PermitException
from permit.openapi.models import RoleCreate, TenantCreate, TenantUpdate, UserCreate
from tests.api.consts import MOCK_API_URL
from tests.api.examples import USER_READ_EXAMPLE


@pytest.mark.parametrize(
    "email", ["name1@domain.com", "name2@domain.com", "name3@domain.com"]
)
async def test_client_sync_user_create(
    api_client: PermitApiClient, httpx_mock, email: str
):
    users_endpoint = "/v2/facts/{proj_id}/{env_id}/users"
    context = api_client._config.context
    user_json = USER_READ_EXAMPLE.copy()
    user_json.update({"email": email, "key": email})

    httpx_mock.add_response(
        method="POST",
        url=f"{MOCK_API_URL}{users_endpoint.format(proj_id=context.project, env_id=context.environment)}",
        json=user_json,
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{MOCK_API_URL}{users_endpoint.format(proj_id=context.project, env_id=context.environment)}/{email}",
        json={},
    )

    create_user = UserCreate(
        key=email,
        email=EmailStr(email),
        first_name="Jane",
        last_name="Doe",
        attributes=user_json["attributes"],
    )
    user = await api_client.sync_user(create_user)
    created_user_dict = user.dict()
    for key, value in create_user.dict().items():
        assert created_user_dict.get(key) == value


@pytest.mark.parametrize(
    "email", ["name1@domain.com", "name2@domain.com", "name3@domain.com"]
)
async def test_client_sync_user_update(api_client: PermitApiClient, email: str):
    create_user = UserCreate(
        key=email,
        email=EmailStr(email),
        first_name="test first name updated",
        last_name="test last name updated",
    )
    user = await api_client.sync_user(create_user)
    created_user_dict = user.dict()
    for key, value in create_user.dict().items():
        assert created_user_dict.get(key) == value


@pytest.mark.parametrize(
    "email", ["name4@domain.com", "name5@domain.com", "name6@domain.com"]
)
async def test_client_sync_user_create_dict(api_client: PermitApiClient, email: str):
    create_user = UserCreate(
        key=email,
        email=EmailStr(email),
        first_name="test first name",
        last_name="test last name",
    ).dict()
    user = await api_client.sync_user(create_user)
    created_user_dict = user.dict()
    for key, value in create_user.items():
        assert created_user_dict.get(key) == value


@pytest.mark.parametrize(
    "email", ["name4@domain.com", "name5@domain.com", "name6@domain.com"]
)
async def test_client_sync_user_update_dict(api_client: PermitApiClient, email: str):
    update_user = UserCreate(
        key=email,
        email=EmailStr(email),
        first_name="test first name updated",
        last_name="test last name updated",
    ).dict()
    user = await api_client.sync_user(update_user)
    updated_user_dict = user.dict()
    for key, value in update_user.items():
        assert updated_user_dict.get(key) == value


@pytest.mark.parametrize(
    "email", ["name1@domain.com", "name2@domain.com", "name3@domain.com"]
)
async def test_client_sync_user_missing_key(api_client: PermitApiClient, email: str):
    create_user = UserCreate(
        key=email,
        email=EmailStr(email),
        first_name="test first name updated",
        last_name="test last name updated",
    ).dict(exclude={"key"})
    with pytest.raises(KeyError):
        await api_client.sync_user(create_user)


@pytest.mark.parametrize(
    "email", ["name1@domain.com", "name2@domain.com", "name3@domain.com"]
)
async def test_client_get_user(api_client: PermitApiClient, email: str):
    user = await api_client.get_user(email)
    assert user.key == email


@pytest.mark.parametrize("tenant_key", ["tenant1", "tenant2", "tenant3"])
async def test_client_create_tenant(api_client: PermitApiClient, tenant_key: str):
    create_tenant = TenantCreate(key=tenant_key, name=tenant_key)
    tenant = (await api_client.create_tenant(create_tenant)).dict()
    for key, value in create_tenant.dict().items():
        assert tenant.get(key) == value


@pytest.mark.parametrize("tenant_key", ["tenant4", "tenant5", "tenant6"])
async def test_client_create_tenant_dict(api_client: PermitApiClient, tenant_key: str):
    create_tenant = TenantCreate(key=tenant_key, name=tenant_key)
    tenant = (await api_client.create_tenant(create_tenant.dict())).dict()
    for key, value in create_tenant.dict().items():
        assert tenant.get(key) == value


@pytest.mark.parametrize("tenant_key", ["tenant1", "tenant2", "tenant3"])
async def test_client_update_tenant(api_client: PermitApiClient, tenant_key: str):
    update_tenant = TenantUpdate(name=f"{tenant_key} updated")
    tenant = (await api_client.update_tenant(tenant_key, update_tenant)).dict()
    for key, value in update_tenant.dict().items():
        assert tenant.get(key) == value


@pytest.mark.parametrize("tenant_key", ["tenant4", "tenant5", "tenant6"])
async def test_client_update_tenant_dict(api_client: PermitApiClient, tenant_key: str):
    update_tenant = TenantUpdate(name=f"{tenant_key} updated")
    tenant = (await api_client.update_tenant(tenant_key, update_tenant.dict())).dict()
    for key, value in update_tenant.dict().items():
        assert tenant.get(key) == value


@pytest.mark.parametrize(
    "tenant_key", ["tenant1", "tenant2", "tenant3", "tenant4", "tenant5", "tenant6"]
)
async def test_client_get_tenant(api_client: PermitApiClient, tenant_key: str):
    res = await api_client.get_tenant(tenant_key)
    assert res.key == tenant_key


@pytest.mark.parametrize("role_key", ["role1", "role2", "role3"])
async def test_client_create_role(api_client: PermitApiClient, role_key: str):
    create_role = RoleCreate(key=role_key, name=role_key)
    role = await api_client.create_role(create_role)
    assert role.key == create_role.key
    assert role.name == create_role.name


@pytest.mark.parametrize("role_key", ["role4", "role5", "role6"])
async def test_client_create_role_dict(api_client: PermitApiClient, role_key: str):
    create_role = RoleCreate(key=role_key, name=role_key)
    role = await api_client.create_role(create_role.dict())
    assert role.key == create_role.key
    assert role.name == create_role.name


@pytest.mark.parametrize(
    ["role_key", "tenant_key", "user_key"],
    [
        ("role1", "tenant1", "name1@domain.com"),
        ("role2", "tenant2", "name2@domain.com"),
        ("role3", "tenant3", "name3@domain.com"),
    ],
)
async def test_client_assign_role(
    api_client: PermitApiClient, role_key: str, tenant_key: str, user_key: str
):
    res = await api_client.assign_role(user_key, role_key, tenant_key)
    assert res.role == role_key
    assert res.user == user_key
    assert res.tenant == tenant_key


@pytest.mark.parametrize(
    ["role_key", "tenant_key", "user_key"],
    [
        ("role1", "tenant1", "name1@domain.com"),
        ("role2", "tenant2", "name2@domain.com"),
        ("role3", "tenant3", "name3@domain.com"),
    ],
)
async def test_client_unassign_role(
    api_client: PermitApiClient, role_key: str, tenant_key: str, user_key: str
):
    res = await api_client.unassign_role(user_key, role_key, tenant_key)
    assert res is None


@pytest.mark.parametrize(
    "email",
    [
        "name1@domain.com",
        "name2@domain.com",
        "name3@domain.com",
        "name4@domain.com",
        "name5@domain.com",
        "name6@domain.com",
    ],
)
async def test_client_delete_user(api_client: PermitApiClient, email: str):
    res = await api_client.delete_user(email)
    assert res is None
    with pytest.raises(PermitException):
        await api_client.get_user(email)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_key", ["role1", "role2", "role3", "role4", "role5", "role6"]
)
async def test_client_delete_role(api_client: PermitApiClient, role_key: str):
    role = await api_client.delete_role(role_key)
    assert role is None
    with pytest.raises(PermitException):
        await api_client.get_role(role_key)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tenant_key", ["tenant1", "tenant2", "tenant3", "tenant4", "tenant5", "tenant6"]
)
async def test_client_delete_tenant(api_client: PermitApiClient, tenant_key: str):
    res = await api_client.tenants.delete(tenant_key)
    assert res is None
    with pytest.raises(PermitException):
        await api_client.get_tenant(tenant_key)


@pytest.mark.parametrize("resource_key", ["res1", "res2", "res3"])
async def test_delete_resource(api_client: PermitApiClient, resource_key: str):
    await api_client.delete_resource(resource_key)
