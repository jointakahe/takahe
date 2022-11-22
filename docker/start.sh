#!/bin/sh

python3 manage.py migrate

exec gunicorn takahe.wsgi:application -b 0.0.0.0:8000
