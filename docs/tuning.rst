Tuning
======

This page contains a collection of tips and settings that can be used to
tune your server based upon its users and the other servers it federates
with.

Federating
----------

Environment Variable:

* ``TAKAHE_REMOTE_TIMEOUT`` is the number of seconds Takahē will allow when
  making remote requests to other Fediverse instances. This may also be a
  tuple of four floats to set the timeouts for connect, read, write, and
  pool. Example ``TAKAHE_REMOTE_TIMEOUT='[0.5, 1.0, 1.0, 0.5]'``


Caching
--------

By default Takakē has caching disabled. The caching needs of a server can
varying drastically based upon the number of users and how interconnected
they are with other servers.

Caching is configured by specifying a cache DSN in the environment variable
``TAKAHE_CACHES_DEFAULT``. The DSN format can be any supported by
`django-cache-url <https://github.com/epicserve/django-cache-url>`_, but
some cache backends will require additional Python packages not installed
by default with Takahē.

**Examples**

* LocMem cache for a small server: ``locmem://default``
* Memcache cache for a service named ``memcache``  in a docker compose file:
  ``memcached://memcache:11211?key_prefix=takahe``
* Multiple memcache cache servers:
  ``memcached://server1:11211,server2:11211``
