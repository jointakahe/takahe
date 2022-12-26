# IDE Development

IDE development and debugging should be possible, and is currently tested/used in PyCharm by some developers.

Please document additional IDEs below if you are familiar with how to set them up.

## PyCharm

To configure full development/debugging in PyCharm, please run through the checklist below:

1. Create a python interpreter within Docker Compose
    1. Go to Settings > Project > Python Interpreter
    2. Add Interpreter > Docker Compose
        * Server: Docker
        * Configuration Files: `docker/docker-compose-split.yml`
        * Service: `app`
    3. Click next and select the auto-populated system interpreter (`/usr/local/bin/python3`)
4. At this point PyCharm will use the interpreter inside docker for package resolution and auto-complete
5. To run/debug Django, create a new run configuration
    1. Create a new `Django Server` configuration
    2. Most details are left as the default, except
        * Port: `8001`
        * Python Interpreter: Set this to the newly created remote interpreter from above (select the version that isn't the project default)
        * Docker Compose Command and Options: `up nginx`
6. All set!

Notes:
* You can choose to use a local interpreter or your docker compose interpreter for the project default. Either works
and your django run/debug configuration will use docker compose at all times
