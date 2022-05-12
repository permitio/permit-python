import pytest
from aioresponses import aioresponses
from pytest_mock import MockerFixture

from permit import Permit
from permit.mutations.client import PermitApiClient


def test_client_no_args():
    with pytest.raises(TypeError):
        Permit()


def test_client_config(client: Permit):
    assert client.config.token == "fake-token"
    assert client.config.pdp == "http://localhost:7000"
    assert client.config.debug_mode is False
    assert client.config.log.label == "Permit.io"
    assert client.config.auto_mapping.enable is False
    assert client.config.multi_tenancy.default_tenant == "default"


def test_mutations_client(sync_client: Permit):
    assert isinstance(sync_client._mutations_client, PermitApiClient)


async def test_client_check_empty(
    client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", payload={})
    spy = mocker.spy(client._enforcer._logger, "_log")
    result = await client.check(
        user="fake-user", action="fake-action", resource="fake-resource"
    )
    assert result is False
    spy.assert_not_called()


async def test_client_check_allow(
    client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", payload={"allow": True})
    spy = mocker.spy(client._enforcer._logger, "_log")
    result = await client.check(
        user="fake-user", action="fake-action", resource="fake-resource"
    )
    assert result is True
    spy.assert_not_called()


async def test_debug_client_check_allow(
    debug_client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", payload={"allow": True})
    spy = mocker.spy(debug_client._enforcer._logger, "_log")
    result = await debug_client.check(
        user="fake-user", action="fake-action", resource="fake-resource"
    )
    assert result is True
    spy.assert_called()
    assert spy.call_args.args[0] == "INFO"
    message = spy.call_args.args[4]
    assert (
        message
        == "permit.check(fake-user, fake-action, fake-resource, tenant: default) = True"
    )


async def test_client_check_deny(
    client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", payload={"allow": False})
    spy = mocker.spy(client._enforcer._logger, "_log")
    result = await client.check(
        user="fake-user", action="fake-action", resource="fake-resource"
    )
    assert result is False
    spy.assert_not_called()


async def test_debug_client_check_deny(
    debug_client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", payload={"allow": False})
    spy = mocker.spy(debug_client._enforcer._logger, "_log")
    result = await debug_client.check(
        user="fake-user", action="fake-action", resource="fake-resource"
    )
    assert result is False
    spy.assert_called()
    assert spy.call_args.args[0] == "INFO"
    message = spy.call_args.args[4]
    assert (
        message
        == "permit.check(fake-user, fake-action, fake-resource, tenant: default) = False"
    )


async def test_client_check_error(
    client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", status=500)
    spy = mocker.spy(client._enforcer._logger, "_log")
    result = await client.check(
        user="fake-user", action="fake-action", resource="fake-resource"
    )
    assert result is False
    spy.assert_called()
    assert spy.call_args.args[0] == "ERROR"
    message = spy.call_args.args[4]
    assert (
        message
        == "error in permit.check(fake-user, fake-action, fake-resource, tenant: default):\nstatus code: 500\nNone"
    )
