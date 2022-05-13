import pytest
from aioresponses import aioresponses
from pytest_mock import MockerFixture

from permit.mutations.sync import PermitApiClient
from permit.sync import Permit


def test_sync_client_no_args():
    with pytest.raises(TypeError):
        Permit()


def test_sync_client_config(sync_client: Permit):
    assert sync_client.config.token == "fake-token"
    assert sync_client.config.pdp == "http://localhost:7000"
    assert sync_client.config.debug_mode is False
    assert sync_client.config.log.label == "Permit.io"
    assert sync_client.config.auto_mapping.enable is False
    assert sync_client.config.multi_tenancy.default_tenant == "default"


def test_mutations_client(sync_client: Permit):
    assert isinstance(sync_client._mutations_client, PermitApiClient)


def test_sync_client_check_empty(
    sync_client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", payload={})
    spy = mocker.spy(sync_client._enforcer._logger, "_log")
    result = sync_client.check(
        user="fake-user", action="fake-action", resource="fake-resource"
    )
    assert result is False
    spy.assert_not_called()


def test_sync_client_check_allow(
    sync_client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", payload={"allow": True})
    spy = mocker.spy(sync_client._enforcer._logger, "_log")
    result = sync_client.check(
        user="fake-user", action="fake-action", resource="fake-resource"
    )
    assert result is True
    spy.assert_not_called()


def test_debug_sync_client_check_allow(
    debug_sync_client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", payload={"allow": True})
    spy = mocker.spy(debug_sync_client._enforcer._logger, "_log")
    result = debug_sync_client.check(
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


def test_sync_client_check_deny(
    sync_client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", payload={"allow": False})
    spy = mocker.spy(sync_client._enforcer._logger, "_log")
    result = sync_client.check(
        user="fake-user", action="fake-action", resource="fake-resource"
    )
    assert result is False
    spy.assert_not_called()


def test_debug_sync_client_check_deny(
    debug_sync_client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", payload={"allow": False})
    spy = mocker.spy(debug_sync_client._enforcer._logger, "_log")
    result = debug_sync_client.check(
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


def test_sync_client_check_error(
    sync_client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", status=500)
    spy = mocker.spy(sync_client._enforcer._logger, "_log")
    result = sync_client.check(
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
