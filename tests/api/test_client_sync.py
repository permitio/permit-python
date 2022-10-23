import pytest
from pydantic import EmailStr

from permit.api.client_sync import PermitSyncApiClient
from permit.exceptions import PermitException
from permit.openapi.models import (
    ResourceCreate,
    RoleCreate,
    TenantCreate,
    TenantUpdate,
    UserCreate,
)


@pytest.mark.parametrize(
    "email", ["name1@domain.com", "name2@domain.com", "name3@domain.com"]
)
def test_client_sync_user_create(sync_api_client: PermitSyncApiClient, email: str):
    create_user = UserCreate(
        key=email,
        email=EmailStr(email),
        first_name="test first name",
        last_name="test last name",
    )
    user = sync_api_client.sync_user(create_user)
    created_user_dict = user.dict()
    for key, value in create_user.dict().items():
        assert created_user_dict.get(key) == value


@pytest.mark.parametrize(
    "email", ["name1@domain.com", "name2@domain.com", "name3@domain.com"]
)
def test_client_sync_user_update(sync_api_client: PermitSyncApiClient, email: str):
    create_user = UserCreate(
        key=email,
        email=EmailStr(email),
        first_name="test first name updated",
        last_name="test last name updated",
    )
    user = sync_api_client.sync_user(create_user)
    created_user_dict = user.dict()
    for key, value in create_user.dict().items():
        assert created_user_dict.get(key) == value


@pytest.mark.parametrize(
    "email", ["name4@domain.com", "name5@domain.com", "name6@domain.com"]
)
def test_client_sync_user_create_dict(sync_api_client: PermitSyncApiClient, email: str):
    create_user = UserCreate(
        key=email,
        email=EmailStr(email),
        first_name="test first name",
        last_name="test last name",
    ).dict()
    user = sync_api_client.sync_user(create_user)
    created_user_dict = user.dict()
    for key, value in create_user.items():
        assert created_user_dict.get(key) == value


@pytest.mark.parametrize(
    "email", ["name4@domain.com", "name5@domain.com", "name6@domain.com"]
)
def test_client_sync_user_update_dict(sync_api_client: PermitSyncApiClient, email: str):
    update_user = UserCreate(
        key=email,
        email=EmailStr(email),
        first_name="test first name updated",
        last_name="test last name updated",
    ).dict()
    user = sync_api_client.sync_user(update_user)
    updated_user_dict = user.dict()
    for key, value in update_user.items():
        assert updated_user_dict.get(key) == value


@pytest.mark.parametrize(
    "email", ["name1@domain.com", "name2@domain.com", "name3@domain.com"]
)
def test_client_sync_user_missing_key(sync_api_client: PermitSyncApiClient, email: str):
    create_user = UserCreate(
        key=email,
        email=EmailStr(email),
        first_name="test first name updated",
        last_name="test last name updated",
    ).dict(exclude={"key"})
    with pytest.raises(KeyError):
        sync_api_client.sync_user(create_user)


@pytest.mark.parametrize(
    "email", ["name1@domain.com", "name2@domain.com", "name3@domain.com"]
)
def test_client_get_user(sync_api_client: PermitSyncApiClient, email: str):
    user = sync_api_client.get_user(email)
    assert user.key == email


@pytest.mark.parametrize("tenant_key", ["tenant1", "tenant2", "tenant3"])
def test_client_create_tenant(sync_api_client: PermitSyncApiClient, tenant_key: str):
    create_tenant = TenantCreate(key=tenant_key, name=tenant_key)
    tenant = (sync_api_client.create_tenant(create_tenant)).dict()
    for key, value in create_tenant.dict().items():
        assert tenant.get(key) == value


@pytest.mark.parametrize("tenant_key", ["tenant4", "tenant5", "tenant6"])
def test_client_create_tenant_dict(
    sync_api_client: PermitSyncApiClient, tenant_key: str
):
    create_tenant = TenantCreate(key=tenant_key, name=tenant_key)
    tenant = (sync_api_client.create_tenant(create_tenant.dict())).dict()
    for key, value in create_tenant.dict().items():
        assert tenant.get(key) == value


@pytest.mark.parametrize("tenant_key", ["tenant1", "tenant2", "tenant3"])
def test_client_update_tenant(sync_api_client: PermitSyncApiClient, tenant_key: str):
    update_tenant = TenantUpdate(name=f"{tenant_key} updated")
    tenant = (sync_api_client.update_tenant(tenant_key, update_tenant)).dict()
    for key, value in update_tenant.dict().items():
        assert tenant.get(key) == value


@pytest.mark.parametrize("tenant_key", ["tenant4", "tenant5", "tenant6"])
def test_client_update_tenant_dict(
    sync_api_client: PermitSyncApiClient, tenant_key: str
):
    update_tenant = TenantUpdate(name=f"{tenant_key} updated")
    tenant = (sync_api_client.update_tenant(tenant_key, update_tenant.dict())).dict()
    for key, value in update_tenant.dict().items():
        assert tenant.get(key) == value


@pytest.mark.parametrize(
    "tenant_key", ["tenant1", "tenant2", "tenant3", "tenant4", "tenant5", "tenant6"]
)
def test_client_get_tenant(sync_api_client: PermitSyncApiClient, tenant_key: str):
    res = sync_api_client.get_tenant(tenant_key)
    assert res.key == tenant_key


@pytest.mark.parametrize("role_key", ["role1", "role2", "role3"])
def test_client_create_role(sync_api_client: PermitSyncApiClient, role_key: str):
    create_role = RoleCreate(key=role_key, name=role_key)
    role = sync_api_client.create_role(create_role)
    assert role.key == create_role.key
    assert role.name == create_role.name


@pytest.mark.parametrize("role_key", ["role4", "role5", "role6"])
def test_client_create_role_dict(sync_api_client: PermitSyncApiClient, role_key: str):
    create_role = RoleCreate(key=role_key, name=role_key)
    role = sync_api_client.create_role(create_role.dict())
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
def test_client_assign_role(
    sync_api_client: PermitSyncApiClient, role_key: str, tenant_key: str, user_key: str
):
    res = sync_api_client.assign_role(user_key, role_key, tenant_key)
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
def test_client_unassign_role(
    sync_api_client: PermitSyncApiClient, role_key: str, tenant_key: str, user_key: str
):
    res = sync_api_client.unassign_role(user_key, role_key, tenant_key)
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
def test_client_delete_user(sync_api_client: PermitSyncApiClient, email: str):
    res = sync_api_client.delete_user(email)
    assert res is None
    with pytest.raises(PermitException):
        sync_api_client.get_user(email)


@pytest.mark.parametrize(
    "role_key", ["role1", "role2", "role3", "role4", "role5", "role6"]
)
def test_client_delete_role(sync_api_client: PermitSyncApiClient, role_key: str):
    role = sync_api_client.delete_role(role_key)
    assert role is None
    with pytest.raises(PermitException):
        sync_api_client.get_role(role_key)


@pytest.mark.parametrize(
    "tenant_key", ["tenant1", "tenant2", "tenant3", "tenant4", "tenant5", "tenant6"]
)
def test_client_delete_tenant(sync_api_client: PermitSyncApiClient, tenant_key: str):
    res = sync_api_client.delete_tenant(tenant_key)
    assert res is None
    with pytest.raises(PermitException):
        sync_api_client.get_tenant(tenant_key)


@pytest.mark.parametrize("resource_key", ["res1", "res2", "res3"])
def test_create_resource(sync_api_client: PermitSyncApiClient, resource_key: str):
    create_resource = ResourceCreate(key=resource_key, name=resource_key, actions={})
    resource = sync_api_client.create_resource(create_resource)
    assert resource.key == create_resource.key
    assert resource.name == create_resource.name


@pytest.mark.parametrize("resource_key", ["res1", "res2", "res3"])
def test_delete_resource(sync_api_client: PermitSyncApiClient, resource_key: str):
    sync_api_client.delete_resource(resource_key)
