import functools

from permit.openapi.api.base import Api
from permit.openapi.api.users import (
    assign_role_to_user,
    create_user,
    delete_user,
    get_user,
    list_users,
    unassign_role_from_user,
    update_user,
)


class UsersApi(Api):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.async_assign_role_to_user = functools.partial(assign_role_to_user.asyncio)
        self.async_create_user = functools.partial(create_user.asyncio)
        self.async_delete_user = functools.partial(delete_user.asyncio)
        self.async_get_user = functools.partial(get_user.asyncio)
        self.async_list_users = functools.partial(list_users.asyncio)
        self.async_unassign_role_from_user = functools.partial(
            unassign_role_from_user.asyncio
        )
        self.async_update_user = functools.partial(update_user.asyncio)
        self.assign_role_to_user = functools.partial(assign_role_to_user.sync)
        self.create_user = functools.partial(create_user.sync)
        self.delete_user = functools.partial(delete_user.sync)
        self.get_user = functools.partial(get_user.sync)
        self.list_users = functools.partial(list_users.sync)
        self.unassign_role_from_user = functools.partial(unassign_role_from_user.sync)
        self.update_user = functools.partial(update_user.sync)
