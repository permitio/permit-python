"""A consumer of the permit SDK, written the way its documentation uses it.

tests/test_typing_surface.py type-checks this file with mypy (see mypy.ini here) and
requires zero errors, so every call below must be both valid at runtime and accepted by
a type checker. The lines marked ``# type: ignore[...]`` are real mistakes that must stay
errors: with warn_unused_ignores, the check fails if one of them stops being reported.
"""

from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from typing_extensions import assert_type

from permit import Permit, PermitApiError, PermitConfig, UserCreate, UserInput, UserRead
from permit.api.elements import UserLoginAsResponse
from permit.api.models import (
    BulkRoleAssignmentReport,
    PaginatedResultUserRead,
    RoleAssignmentCreate,
    RoleAssignmentRead,
    RoleCreate,
    RoleRead,
    TenantCreate,
    TenantRead,
    UserCreateBulkOperationResult,
)
from permit.enforcement.enforcer import CheckQuery
from permit.pdp_api.models import RoleAssignment
from permit.pdp_api.pdp_api_client import SyncRoleAssignmentsApi
from permit.sync import Permit as SyncPermit

CONFIG = PermitConfig(token="permit_key_x", pdp="http://localhost:7766")

_Parameter = TypeVar("_Parameter")


def parameter_type(method: Callable[[_Parameter], object]) -> _Parameter:
    """Stands for the type of ``method``'s only parameter, for ``assert_type`` to compare.

    A dict argument type-checks against a bare ``dict`` parameter as well as against
    ``Dict[str, Any]``, so only the parameter's own type shows the difference, which
    pyright's strict mode reports as partially unknown.
    """
    raise NotImplementedError


async def async_client() -> None:
    permit = Permit(CONFIG)
    Permit(token="permit_key_x", pdp="http://localhost:7766")
    assert_type(permit.config, PermitConfig)

    assert_type(await permit.check("user", "read", "document"), bool)
    assert_type(
        await permit.check({"key": "u", "attributes": {"dept": "eng"}}, "read", {"type": "document", "tenant": "t1"}),
        bool,
    )
    assert_type(await permit.bulk_check([{"user": "u", "action": "read", "resource": "document"}]), List[bool])
    assert_type(await permit.get_user_permissions("u"), Dict[str, Any])

    # Optional model fields are optional to the type checker too.
    user = UserCreate(key="u")
    tenant = TenantCreate(key="t1", name="T1")
    role = RoleCreate(key="admin", name="Admin", permissions=["document:read"])
    # Email fields take a plain str, as they do at runtime.
    UserCreate(key="u", email="u@example.com")
    # UserInput takes each aliased field by name or by alias, as it does at runtime.
    UserInput(key="u", first_name="A", last_name="B")
    UserInput(key="u", firstName="A", lastName="B")

    # Every method that validates its arguments takes the model or an equivalent dict.
    assert_type(await permit.api.users.create(user), UserRead)
    assert_type(await permit.api.users.create({"key": "u2"}), UserRead)
    assignment = RoleAssignmentCreate(user="u", role="admin", tenant="t1")
    assert_type(await permit.api.users.assign_role(assignment), RoleAssignmentRead)
    assert_type(await permit.api.users.assign_role({"user": "u", "role": "admin", "tenant": "t1"}), RoleAssignmentRead)
    assert_type(await permit.api.users.bulk_create([user, {"key": "u3"}]), UserCreateBulkOperationResult)
    assert_type(await permit.api.tenants.create(tenant), TenantRead)
    await permit.api.tenants.bulk_create([{"key": "t2", "name": "T2"}])
    assert_type(await permit.api.roles.create(role), RoleRead)
    await permit.api.resources.create({"key": "document", "name": "Document", "actions": {"read": {}}})
    assert_type(
        await permit.api.role_assignments.bulk_assign([{"user": "u", "role": "admin", "tenant": "t1"}]),
        BulkRoleAssignmentReport,
    )
    await permit.api.users.sync({"key": "u", "email": "u@example.com"})

    # A list built before a bulk call is accepted too, whether of models or of dicts.
    users = [UserCreate(key=key) for key in ("u4", "u5")]
    await permit.api.users.bulk_create(users)
    tenant_dicts: List[Dict[str, Any]] = [{"key": "t3", "name": "T3"}]
    await permit.api.tenants.bulk_create(tenant_dicts)
    assignments = [RoleAssignmentCreate(user=key, role="admin", tenant="t1") for key in ("u4", "u5")]
    await permit.api.role_assignments.bulk_assign(assignments)

    # The deprecated facade keeps the signatures of the methods it wraps.
    assert_type(await permit.api.get_user("u"), UserRead)
    assert_type(await permit.api.create_tenant({"key": "t4", "name": "T4"}), TenantRead)

    # Results are pydantic v1 models under either pydantic major.
    fetched = await permit.api.users.get("u")
    assert_type(fetched.dict(), Dict[str, Any])
    assert_type(fetched.key, str)
    assert_type(fetched.email, Optional[str])

    try:
        await permit.api.users.get("missing")
    except PermitApiError as error:
        assert_type(error.status_code, int)


def dict_parameters(query: CheckQuery) -> None:
    permit = Permit(CONFIG)
    sync_permit = SyncPermit(CONFIG)

    assert_type(query["user"], Union[Dict[str, Any], str])
    assert_type(query["resource"], Union[Dict[str, Any], str])
    assert_type(parameter_type(permit.api.users.sync), Union[UserCreate, Dict[str, Any]])
    assert_type(parameter_type(sync_permit.api.users.sync), Union[UserCreate, Dict[str, Any]])
    assert_type(parameter_type(sync_permit.api.create_tenant), Union[TenantCreate, Dict[str, Any]])


def sync_client() -> None:
    permit = SyncPermit(CONFIG)

    assert_type(permit.check("user", "read", "document"), bool)
    assert_type(permit.get_user_permissions("u"), Dict[str, Any])
    assert_type(permit.api.users.get("u"), UserRead)
    assert_type(permit.api.users.list(), PaginatedResultUserRead)
    assert_type(permit.api.tenants.create(TenantCreate(key="t1", name="T1")), TenantRead)
    assert_type(permit.api.tenants.list(), List[TenantRead])
    assert_type(permit.api.users.create({"key": "u2"}), UserRead)
    permit.api.users.assign_role({"user": "u", "role": "admin", "tenant": "t1"})
    permit.api.users.bulk_create([UserCreate(key="u3"), {"key": "u4"}])
    users: List[UserCreate] = [UserCreate(key="u5")]
    permit.api.users.bulk_replace(users)
    assert_type(permit.api.get_user("u"), UserRead)
    assert_type(permit.elements.login_as("u", "t1"), UserLoginAsResponse)
    pdp_role_assignments: SyncRoleAssignmentsApi = permit.pdp_api.role_assignments
    assert_type(pdp_role_assignments.list(), List[RoleAssignment])
    for listed in permit.api.users.list().data:
        assert_type(listed.key, str)


async def mistakes_stay_errors() -> None:
    permit = Permit(CONFIG)
    sync_permit = SyncPermit(CONFIG)

    # A required field is still required.
    UserCreate()  # type: ignore[call-arg]
    PermitConfig()  # type: ignore[call-arg]
    # Accepting both spellings of an aliased field does not mean accepting any name.
    UserInput(key="u", firstname="A")  # type: ignore[call-arg]
    # Accepting dicts does not mean accepting anything.
    await permit.api.users.create("u")  # type: ignore[arg-type]
    # SDK models are pydantic v1 models, so the pydantic v2 API does not exist on them.
    UserCreate(key="u").model_dump()  # type: ignore[attr-defined]
    # The blocking client returns values, not awaitables.
    await sync_permit.api.users.get("u")  # type: ignore[misc]
    # The async client returns awaitables, not values.
    _ = permit.api.users.get("u").email  # type: ignore[attr-defined]
