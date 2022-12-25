#!/bin/bash

# Set up cache size
CACHE_SIZE="${TAKAHE_NGINX_CACHE_SIZE:-1g}"
sed -i s/__CACHESIZE__/${CACHE_SIZE}/g /takahe/docker/nginx.conf

# Enable auto-reload when in DEBUG mode
[ "${TAKAHE_DEBUG}" = "true" ] && GUNICORN_RELOAD="--reload"

# Run nginx and gunicorn
nginx -c "/takahe/docker/nginx.conf" &

echo $GUNICORN_RELOAD 4
gunicorn takahe.wsgi:application -b 0.0.0.0:8001 $GUNICORN_RELOAD &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
