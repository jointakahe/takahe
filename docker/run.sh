#!/bin/bash

function run_gunicorn() {
  # Provide hook for disable gunicorn in development
  [ -n "$DISABLE_GUNICORN_RUN" ] && echo "gunicorn disabled" && return

  gunicorn takahe.wsgi:application -b 0.0.0.0:8001 $GUNICORN_EXTRA_CMD_ARGS &
}

function run_nginx() {
  # Provide hook for disabling nginx in development
  [ -n "$DISABLE_NGINX_RUN" ] && echo "nginx disabled" && return

  # Reset the rendered file before rewriting below
  cp /takahe/docker/nginx.conf /takahe/docker/nginx.rendered.conf

  # Set up cache size
  CACHE_SIZE="${TAKAHE_NGINX_CACHE_SIZE:-1g}"
  sed -i s/__CACHESIZE__/${CACHE_SIZE}/g /takahe/docker/nginx.rendered.conf

  # Set the gunicorn host (used primarily for development override)
  NGINX_GUNICORN_HOST="${NGINX_GUNICORN_HOST:-127.0.0.1}"
  sed -i s/__GUNICORN_HOST__/${NGINX_GUNICORN_HOST}/g /takahe/docker/nginx.rendered.conf

  # Run nginx and gunicorn
  nginx -c "/takahe/docker/nginx.rendered.conf" &
}

run_nginx

run_gunicorn

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
