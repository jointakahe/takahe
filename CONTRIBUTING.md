# Contributing to Takahē

## Getting Started

Development can be done "bare metal" or with Docker.  We'll describe both here.


### Bare Metal

Takahē requires Python 3.11, so you'll need that first.  Then, create and
activate a virtual environment:

```shell
$ python3 -m venv .venv
$ . .venv/bin/activate
```

You can install the development requirements:

```shell
$ pip install -r requirements-dev.txt
```

...and enable git commit hooks if you like:

```bash
$ pre-commit install
```

Finally, you can run the tests with PyTest:

```bash
$ pytest
```


### Docker

The docker build process will take care of much of the above, but you just have
to be sure that you're executing it from the project root.

First, you need to build your image:

```shell
$ docker build -f ./docker/Dockerfile -t "takahe:latest" .
```

Then start the `compose` session:

```shell
$ docker compose -f docker/docker-compose.yml up
```

Once your session is up and running, you can run the tests inside your
container:

```shell
$ docker compose -f docker/docker-compose.yml exec web pytest
```


# Code of Conduct

As a contributor, you can help us keep the Takahē community open and inclusive. Takahē
follows the [Django Project Code of Conduct](https://www.djangoproject.com/conduct/).
