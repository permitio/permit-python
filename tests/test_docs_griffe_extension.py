"""The API reference site's Griffe extension, scripts/docs_griffe_extension.py.

Griffe reads the SDK the way the site's build does, statically and with the extension, and
these tests check what the site would show: blocking signatures for the blocking classes,
taken from the stub by full path, deprecation labels, pydantic field descriptions, and a
models page that lists exactly the models the SDK's methods take and return.
"""

from collections.abc import Iterator
from pathlib import Path

import griffe
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENSION = REPO_ROOT / "scripts" / "docs_griffe_extension.py"
MODELS_PAGE = REPO_ROOT / "docs" / "reference" / "models.md"


@pytest.fixture(scope="module")
def permit_package() -> griffe.Module:
    """The permit package as the site's build reads it."""
    package = griffe.load(
        "permit",
        search_paths=[REPO_ROOT],
        extensions=griffe.load_extensions(str(EXTENSION)),
        docstring_parser="google",
        allow_inspection=False,
    )
    assert isinstance(package, griffe.Module)
    return package


def walk_modules(module: griffe.Module) -> Iterator[griffe.Module]:
    yield module
    for submodule in module.modules.values():
        yield from walk_modules(submodule)


def test_blocking_rest_api_classes_are_the_stub_classes(permit_package: griffe.Module) -> None:
    module = permit_package["api.sync_api_client"]
    blocking = [name for name in module.members if name.startswith("Sync") and "Api" in name]
    assert "SyncRolesApi" in blocking
    assert "SyncPermitApiClient" in blocking

    for name in blocking:
        member = module.members[name]
        if name == "SyncPermitApiClient":
            assert not member.is_alias
            continue
        assert member.is_alias, name
        assert member.final_target.path == f"permit._sync_types.{name}"

    roles_list = module["SyncRolesApi"].members["list"]
    assert "async" not in roles_list.labels
    assert str(roles_list.returns) == "list[RoleRead]"


def test_the_async_client_methods_are_labelled_async(permit_package: griffe.Module) -> None:
    assert "async" in permit_package["api.roles.RolesApi.list"].labels
    assert "async" in permit_package["permit.Permit.check"].labels
    assert "async" not in permit_package["sync.Permit.check"].labels


def test_pdp_role_assignments_are_matched_by_full_path_not_by_name(
    permit_package: griffe.Module,
) -> None:
    # permit.pdp_api and permit.api both have a SyncRoleAssignmentsApi. Matched by name,
    # the PDP one would show the REST API's methods.
    pdp = permit_package["pdp_api.pdp_api_client.SyncRoleAssignmentsApi"]
    rest = permit_package["api.sync_api_client.SyncRoleAssignmentsApi"]

    assert pdp.final_target.path == "permit._sync_types.SyncPdpRoleAssignmentsApi"
    assert rest.final_target.path == "permit._sync_types.SyncRoleAssignmentsApi"
    assert set(pdp.members) == {"list"}
    assert {"assign", "unassign", "bulk_assign"} <= set(rest.members)
    pdp_list = [parameter.name for parameter in pdp.members["list"].parameters]
    assert "resource_instance_key" in pdp_list
    assert "async" not in pdp.members["list"].labels


def test_no_class_made_blocking_at_runtime_is_documented(permit_package: griffe.Module) -> None:
    """A class with the SyncClass metaclass has async methods in the source."""
    runtime_blocking = [
        cls.path
        for module in walk_modules(permit_package)
        for cls in module.classes.values()
        if not cls.is_alias and "metaclass" in cls.keywords
    ]
    assert runtime_blocking == []


def test_names_bound_in_both_branches_show_the_type_checking_one(
    permit_package: griffe.Module,
) -> None:
    assert str(permit_package["enforcement.enforcer.User"].value) == "dict[str, Any] | str"
    model_input = permit_package["utils.model_input.ModelInput"]
    assert model_input.is_attribute
    assert str(model_input.value) == "_Model | dict[str, Any]"
    # A runtime import is left alone: the models import pydantic per major.
    assert permit_package["api.models.EmailStr"].is_alias


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        ("api.deprecated.DeprecatedApi.get_user", "use permit.api.users.get() instead."),
        ("api.sync_api_client.SyncDeprecatedApi.get_user", "use permit.api.users.get() instead."),
        ("api.tenants.TenantsApi.add_user", "use permit.api.tenants.create_user() instead."),
        ("api.sync_api_client.SyncTenantsApi.add_user", "use permit.api.tenants.create_user()"),
        ("exceptions.PermitException", "catch PermitConnectionError instead"),
    ],
)
def test_deprecations_are_labelled_with_their_message(
    permit_package: griffe.Module, path: str, replacement: str
) -> None:
    obj = permit_package[path]
    assert "deprecated" in obj.labels
    sections = obj.docstring.parsed
    notice = sections[-1]
    assert notice.kind is griffe.DocstringSectionKind.admonition
    assert notice.title == "Deprecated"
    assert "will be removed in permit 4.0" in notice.value.contents
    assert replacement in notice.value.contents


def test_methods_that_are_not_deprecated_carry_no_label(permit_package: griffe.Module) -> None:
    assert "deprecated" not in permit_package["api.tenants.TenantsApi.create_user"].labels
    stub = permit_package["api.sync_api_client.SyncTenantsApi"]
    assert "deprecated" not in stub.members["create_user"].labels


def test_pydantic_fields_are_documented_from_their_field_call(
    permit_package: griffe.Module,
) -> None:
    role = permit_package["api.models.RoleRead"]

    name = role.members["name"]
    assert name.docstring.value == "The name of the role"
    assert name.value is None  # required: Field(...)

    description = role.members["description"]
    assert str(description.value) == "None"
    assert description.docstring.value.startswith("optional description string")

    # The description's own indentation and surrounding newlines are dropped.
    granted_to = role.members["granted_to"].docstring.value
    assert granted_to.startswith("A derived role")
    assert "\n        " not in granted_to

    attributes = permit_package["enforcement.interfaces.TenantDetails.attributes"]
    assert str(attributes.value) == "dict()"
    assert role.members["v1compat_settings"].docstring is None


def public_signature_models(package: griffe.Module) -> set[str]:
    """The permit.api.models names in the signatures of the SDK's public methods."""
    found = set()
    for module in walk_modules(package):
        if module.path == "permit.api.models":
            continue
        for cls in module.classes.values():
            if cls.is_alias:
                continue
            for name, member in cls.members.items():
                if name.startswith("_"):
                    continue
                if isinstance(member, griffe.Function):
                    annotations = [p.annotation for p in member.parameters] + [member.returns]
                elif isinstance(member, griffe.Attribute) and "property" in member.labels:
                    annotations = [member.annotation]
                else:
                    continue
                for annotation in annotations:
                    if not isinstance(annotation, griffe.Expr):
                        continue
                    for part in annotation.iterate(flat=True):
                        if isinstance(part, griffe.ExprName):
                            module_path, _, model = part.canonical_path.rpartition(".")
                            if module_path == "permit.api.models":
                                found.add(model)
    return found


def models_on_page() -> list[str]:
    options = MODELS_PAGE.read_text().split("      members:\n", 1)[1]
    return [
        line.removeprefix("        - ")
        for line in options.splitlines()
        if line.startswith("        - ")
    ]


def test_the_models_page_lists_the_models_of_public_signatures(
    permit_package: griffe.Module,
) -> None:
    listed = models_on_page()
    expected = public_signature_models(permit_package)

    assert "RoleRead" in expected
    assert "UserCreate" in expected
    missing = sorted(expected - set(listed))
    extra = sorted(set(listed) - expected)
    page = MODELS_PAGE.relative_to(REPO_ROOT)
    assert not missing, f"Add these models to the members list in {page}: {missing}"
    assert not extra, f"No public method takes or returns these; remove them: {extra}"
    assert listed == sorted(listed, key=str.lower), "Keep the members list alphabetical."


def test_a_deprecation_message_it_cannot_read_fails_the_load() -> None:
    package = {
        "__init__.py": "",
        "api.py": (
            "from permit.utils.deprecation import deprecated\n"
            "MESSAGE = 'gone'\n"
            "class Api:\n"
            "    @deprecated(MESSAGE)\n"
            "    async def old(self) -> None:\n"
            '        """Old."""\n'
        ),
    }
    extensions = griffe.load_extensions(str(EXTENSION))
    with (
        pytest.raises(ValueError, match="Cannot read the deprecation message 'MESSAGE'"),
        griffe.temporary_visited_package("deprecations", package, extensions=extensions),
    ):
        pass
