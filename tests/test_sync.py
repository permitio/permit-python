import aiohttp
import pytest
from aioresponses import aioresponses
from pytest_mock import MockerFixture

from permit.exceptions import PermitConnectionError, PermitException
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
        == "permit.check(key='fake-user' firstName=None lastName=None email=None roles=None attributes=None, fake-action, fake-resource, tenant: default) = True"
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
        == "permit.check(key='fake-user' firstName=None lastName=None email=None roles=None attributes=None, fake-action, fake-resource, tenant: default) = False"
    )


def test_sync_client_check_error(
    sync_client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post("http://localhost:7000/allowed", status=500)
    with pytest.raises(PermitException) as exc:
        sync_client.check(
            user="fake-user", action="fake-action", resource="fake-resource"
        )
    assert "Permit SDK got unexpected status code: 500" in str(exc.value)


def test_client_check_no_connection_when_pdp_is_down(
    sync_client: Permit, mock_aioresponse: aioresponses, mocker: MockerFixture
):
    mock_aioresponse.post(
        "http://localhost:7000/allowed",
        exception=aiohttp.ClientError("Cannot connect to host"),
    )
    with pytest.raises(PermitConnectionError) as exc:
        sync_client.check(
            user="fake-user", action="fake-action", resource="fake-resource"
        )
    assert "cannot connect to the PDP container" in str(exc.value)
