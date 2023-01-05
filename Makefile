.PHONY: image docs compose_build compose_up compose_down

image:
	docker build -t takahe -f docker/Dockerfile .

docs:
	cd docs/ && make html

compose_build:
	docker-compose -f docker/docker-compose.yml build

compose_up:
	docker-compose -f docker/docker-compose.yml up

compose_down:
	docker-compose -f docker/docker-compose.yml down

# Development Setup
.venv:
	python3 -m venv .venv
	. .venv/bin/activate
	python3 -m pip install -r requirements-dev.txt

.git/hooks/pre-commit: .venv
	python3 -m pre_commit install

.env:
	# afterwords, set in .env
	# TAKAHE_DATABASE_SERVER="postgres://postgres:insecure_password@localhost:5433/takahe"
	cp development.env .env

_PHONY: pydev
pydev: .venv

_PHONY: precommit
precommit: pydev .git/hooks/pre-commit

_PHONY: startdb stopdb
startdb:
	docker compose -f docker/docker-compose.yml up db -d

stopdb:
	docker compose -f docker/docker-compose.yml stop db

_PHONY: superuser
superuser: .env pydev startdb
	python3 -m manage createsuperuser

_PHONY: pydev
pydev: pydev precommit

_PHONY: test
test: pydev
	python3 -m pytest

# Active development
_PHONY: migrations server stator
migrations: startdb
	python3 -m manage migrate

server: startdb
	python3 -m manage runserver

stator: startdb
	python3 -m manage runstator
