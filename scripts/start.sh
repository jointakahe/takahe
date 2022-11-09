#!/bin/sh

. /takahe/.venv/bin/activate

python manage.py migrate

exec gunicorn takahe.asgi:application -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
