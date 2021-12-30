# Permit.io Python SDK

This instructions are for the pre-release version of the python SDK (0.0.1).

# Permit.io microservice setup (PDP)
The **PDP container** is a component that is installed within your network and can respond to authorization queries within the normal SLA times of your server. It caches the authorization policies relevant to your service and fetches policy updates as needed.

The easiest way to deploy the **PDP** is as a sidecar.

### 1) Getting the docker image
The container image is available in docker hub.
```
docker pull permitio/sidecar
```

### 2) Running in docker
```
docker run -p 8000:8000 --env CLIENT_TOKEN=[Your token] permitio/sidecar:0.1.0
```
this command will use port 8000 on your machine as the server port for the sidecar.

### 3) Running in kubernetes (TBD)
If you are running on Kubernetes, we recommend using our provided helm chart available here (TBD).

Run the following commands:
```
helm repo add permitio https://helm.permit.io
helm repo update
helm install --name my-release permitio/sidecar --set client.token=[Your Token]
```

# SDK setup (python)
This section explains how to install the sdk in your python project.

### 1) installing the sdk into your virtual environment
```
pip install permit
```
### 2) Getting the client token
Before importing the sdk in your code you will need to possess a `client_token`.
The `client_token` identifies your app and allows access to sensitive authorization settings.

Treat the `client_token` as a cryptographic secret and store it in a safe place (e.g: hashicorp vault, github repository secrets, etc). **Do not store the token in your repo.**

### 3) importing the sdk in your code

Note: Your program which includes the sdk should declare the `SIDECAR_URL` env var.
The default value is `http://localhost:7000`, if you deployed the sidecar container to another location, change this env var accordingly.

In the application startup code (before any requests are served, etc) - in most apps it would be `__main__`, call `permit.init()` like so:
```
import permit

if __name__ == "__main__":
    permit.init(
        token="<client_token>",
        app_name="<your application name>",
        service_name="<your microservice name>"
    )
    # Your program starts here
```

#### **More examples**
in `flask`, the best place to put `permit.init()` would be in the `before_first_request` hook:
```
import permit
from flask import Flask

app = Flask(__name__)

@app.before_first_request
def init_authorization():
    permit.init(...)
```

in `fastapi`, the best place to put `permit.init()` would be in the `startup` event:
```
import permit
from fastapi import FastAPI

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    permit.init(...)
```

### Resource and Action registration
As you probably know by now, authorization dictates which people or machines (called **users** or **actors** in our service) can run which **actions** on which **resources**.

The policy configuration itself is managed by you in our cloud dashboard. But in order to know **where** to enforce authorization, you must declare which **actions** and **resources** you want to protect.

There are three ways to declare resources and actions in our system:

1. Automatically in your code via instrumentation

Currently only supported for `fastapi` and `flask`. in your code, after declaring the app, call:
```
permit.protect(app)
```
By default, all HTTP endpoints will be registered as resources. Actions will be defined according to HTTP verbs.

2. Manually in your code
via calls to `permit.resource()` and `permit.action()`.

```
import permit

permit.resource(
    name="task",
    description="Todo Task",
    type="rest",
    path="/api/v1/boards/{list_id}/tasks",
    actions=[
        permit.action(
            name="list",
            title="List",
            description="list all tasks",
            path="/api/v1/boards/{list_id}/tasks",
            attributes={
                "verb": "GET"
            }
        ),
        permit.action(
            name="retrieve",
            title="Retrieve",
            description="Retrieve task details",
            path="/api/v1/boards/{list_id}/tasks/{task_id}",
            attributes={
                "verb": "GET"
            }
        ),
        # more actions ...
    ]
)
```
Each call to permit.resource() potentially generates a call to the cloud service in order to sync the resource to our system. Thus, it’s best to call permit.resource() outside of the request flow (not in every request).

### Parameters
Each resource has the following params:
- **name**: the name of the resource, must be unique.
- **description** (optional): description for humans.
- **type**: type of the resource, i.e **rest** for Restful apis, etc.
- **path**: a relative URI/URN identifying the resource in your system. Does not have to be related to a publicly available api.
- **actions**: an array containing the actions on that resource. each item in the array must be declared using `permit.action()`.

Each action has the following params:
- **name**: the name of the action, must be unique per resource.
- **title** (optional): a nicer name of the action, displayed in the dashboard.
- **description** (optional): description for humans.
- **path** (optional): a relative URI/URN identifying the action in your system. If your routes do not correspond to the REST standard, this field overrides `resource.path` for this action.
- **attributes** (optional): a dict of metadata for your action.

### Path variables
Notice that the paths can contain variables (context). In the next line, notice that list_id and task_id will be interpreted as variables:
```
/api/v1/boards/{list_id}/tasks/{task_id}
```

If you will later run the following query
```
permit.is_allowed(user, action, "/api/v1/boards/2/tasks/3")
```
our sdk will automatically know to associate: `list_id=2`, `task_id=3`

3. Manually via the dashboard interface (TBD)
We are working on adding resources and actions via the dashboard.

# Applying enforcement

### 1. Calling is_allowed()

`permit.is_allowed()` is the single most important method in the sdk. It allows you to query whether or not a user can perform an action on a resource in a certain context.

Calling is allowed in your code:
```
if not permit.is_allowed(user, action, resource):
    raise HTTPException(status_code = status.HTTP_403_FORBIDDEN)
```

`is_allowed()` returns a boolean (`true`/`false`): whether or not to allow the action.

#### **Function parameters:**
- **user**: the user performing the action. Can be a string (e.g: user id) or a JWT (json web token). The user id can either be generated by you or by an identity provider like Auth0. Permit.io does not care what this id is as long as it uniquely identifies the user and is consistent.
- **action**: a string identifying the action.
- **resource**: a string (URI/URN) or a class instance identifying the resource.

If no matching action/resource are found on the system the request will be automatically denied and `false` will be returned. This can happen if you never declared your resources and actions using either `permit.action()` / `permit.resource()` or the automated `permit.protect()`.


## Connecting with your Authentication (JWT)
