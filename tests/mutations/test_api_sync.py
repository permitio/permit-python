import pytest
from aioresponses import aioresponses
from pytest_mock import MockerFixture

from permit.config import PermitConfig
from permit.enforcement.interfaces import UserInput
from permit.mutations.client import Tenant
from permit.mutations.sync import PermitApiClient


@pytest.fixture
def api_client():
    return PermitApiClient(PermitConfig())


def test_get_user(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.get("http://localhost:7000/cloud/users/123", payload={"id": "123"})
    spy = mocker.spy(api_client._logger, "_log")
    result = api_client.get_user("123")
    assert result == {"id": "123"}
    spy.assert_not_called()


def test_get_role(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.get("http://localhost:7000/cloud/roles/abc", payload={"id": "abc"})
    spy = mocker.spy(api_client._logger, "_log")
    result = api_client.get_role("abc")
    assert result == {"id": "abc"}
    spy.assert_not_called()


def test_get_tenant(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.get(
        "http://localhost:7000/cloud/tenants/123", payload={"id": "123"}
    )
    spy = mocker.spy(api_client._logger, "_log")
    result = api_client.get_tenant("123")
    assert result == {"id": "123"}
    spy.assert_not_called()


def test_get_assigned_roles(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.get(
        "http://localhost:7000/cloud/role_assignments?user=123", payload={"role": "foo"}
    )
    spy = mocker.spy(api_client._logger, "_log")
    result = api_client.get_assigned_roles("123", None)
    assert result == {"role": "foo"}
    spy.assert_not_called()


def test_get_assigned_roles_with_tenant(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.get(
        "http://localhost:7000/cloud/role_assignments?user=123&tenant=t1",
        payload={"role": "foo"},
    )
    spy = mocker.spy(api_client._logger, "_log")
    result = api_client.get_assigned_roles("123", "t1")
    assert result == {"role": "foo"}
    spy.assert_not_called()


def test_sync_user(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.put("http://localhost:7000/cloud/users", payload={"status": "ok"})
    spy = mocker.spy(api_client._logger, "_log")
    data = UserInput(key="123", firstName="John", lastName="Doe")
    result = api_client.sync_user(data)
    assert result == {"status": "ok"}
    spy.assert_not_called()


def test_delete_user(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.delete("http://localhost:7000/cloud/users/987", status=204)
    spy = mocker.spy(api_client._logger, "_log")
    result = api_client.delete_user("987")
    assert result == {"status": 204}
    spy.assert_not_called()


def test_create_tenant(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.put(
        "http://localhost:7000/cloud/tenants", payload={"status": "ok"}
    )
    spy = mocker.spy(api_client._logger, "_log")
    data = Tenant(key="xxx", name="Fake Tenant")
    result = api_client.create_tenant(data)
    assert result == {"status": "ok"}
    spy.assert_not_called()


def test_update_tenant(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.patch(
        "http://localhost:7000/cloud/tenants/xxx", payload={"status": "ok"}
    )
    spy = mocker.spy(api_client._logger, "_log")
    data = Tenant(key="xxx", name="Fake Tenant")
    result = api_client.update_tenant(data)
    assert result == {"status": "ok"}
    spy.assert_not_called()


def test_delete_tenant(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.delete("http://localhost:7000/cloud/tenants/xxx", status=204)
    spy = mocker.spy(api_client._logger, "_log")
    result = api_client.delete_tenant("xxx")
    assert result == {"status": 204}
    spy.assert_not_called()


def test_assign_role(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post(
        "http://localhost:7000/cloud/role_assignments", payload={"status": "updated"}
    )
    spy = mocker.spy(api_client._logger, "_log")
    result = api_client.assign_role("user1", "role2", "tenant3")
    assert result == {"status": "updated"}
    spy.assert_not_called()


def test_unassign_role(
    api_client: PermitApiClient, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.delete(
        "http://localhost:7000/cloud/role_assignments?role=role2&user=user1&scope=tenant3",
        payload={"status": "deleted"},
    )
    spy = mocker.spy(api_client._logger, "_log")
    result = api_client.unassign_role("user1", "role2", "tenant3")
    assert result == {"status": "deleted"}
    spy.assert_not_called()
