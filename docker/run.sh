#!/bin/bash

# Set up cache size
CACHE_SIZE="${TAKAHE_NGINX_CACHE_SIZE:-1g}"
sed s/__CACHESIZE__/${CACHE_SIZE}/g /takahe/docker/nginx.conf > /takahe/docker/nginx.rendered.conf

# Run nginx and gunicorn
nginx -c "/takahe/docker/nginx.rendered.conf" &

gunicorn takahe.wsgi:application -b 0.0.0.0:8001 $GUNICORN_EXTRA_CMD_ARGS &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
