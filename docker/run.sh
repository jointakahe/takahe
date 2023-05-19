#!/bin/bash

# Set up cache size and nameserver subs
# Nameservers are taken from /etc/resolv.conf - if the IP contains ":", it's IPv6 and must be enclosed in [] for nginx
CACHE_SIZE="${TAKAHE_NGINX_CACHE_SIZE:-1g}"
NAMESERVER=`cat /etc/resolv.conf | grep "nameserver" | awk '{print ($2 ~ ":") ? "["$2"]" : $2}' | tr '\n' ' '`
if [ -z "$NAMESERVER" ]; then
    NAMESERVER="9.9.9.9 149.112.112.112"
fi
sed "s/__CACHESIZE__/${CACHE_SIZE}/g" /etc/nginx/conf.d/default.conf.tpl | sed "s/__NAMESERVER__/${NAMESERVER}/g" > /etc/nginx/conf.d/default.conf

# Run nginx and gunicorn
nginx &

gunicorn takahe.wsgi:application -b 0.0.0.0:8001 $GUNICORN_EXTRA_CMD_ARGS &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
