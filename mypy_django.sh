#!/usr/bin/env bash

set -o errexit

# Change directory to the project root directory.
cd "$(dirname "$0")"

# The HEAD version of django-stubs is required due to unreleased fixes
pip install --quiet --no-input \
  -r requirements-dev.txt \
  types-pyopenssl \
  types-bleach \
  types-mock \
  types-cachetools \
  types-python-dateutil \
  types-docutils \
  mypy \
  git+https://github.com/typeddjango/django-stubs.git@master

export TAKAHE_DATABASE_SERVER="postgres://x@example.com/x"
python3 manage.py collectstatic --noinput

mypy --config-file .mypy_django.ini --ignore-missing-imports --exclude '^venv/' --exclude '^.venv/' --exclude '^tests/' .
