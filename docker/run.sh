#!/bin/bash

# Set up cache size
CACHE_SIZE="${TAKAHE_NGINX_CACHE_SIZE:-1g}"
sed -i s/__CACHESIZE__/${CACHE_SIZE}/g /takahe/docker/nginx.conf

exec nginx -c "/takahe/docker/nginx.conf"
