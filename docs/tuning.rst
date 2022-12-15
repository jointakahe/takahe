Tuning
======

This page contains a collection of tips and settings that can be used to
tune your server based upon its users and the other servers it federates
with.

We recommend that all installations are run behind a CDN, and
have caches configured. See below for more details on each.


CDNs
----

Takahē is *designed to be run behind a CDN*. It serves most static files directly
from its main webservers, which is inefficient if called directly, but they
have ``Cache-Control`` headers set so that the CDN can do the heavy lifting -
more efficiently than offloading all files to something like S3.

If you don't run behind a CDN, things will still work, but even a medium
level of traffic might put the webservers under a lot of load.

If you do run behind a CDN, ensure that your CDN is set to respect
``Cache-Control`` headers from the origin. Some CDNs go purely off of file
extensions by default, which will not capture all of the proxy views Takahē
uses to show remote images without leaking user information.

If you don't want to use a CDN but still want a performance improvement, a
read-through cache that respects ``Cache-Control``, like Varnish, will
also help if placed in front of Takahē.


Scaling
-------

The only bottleneck, and single point of failure in a Takahē installation is
its database; no permanent state is stored elsewhere.

Provided your database is happy (and PostgreSQL does a very good job of just
using more resources if you give them to it), you can:

* Run more webserver containers to handle a higher request load (requests
  come from both users and other ActivityPub servers trying to forward you
  messages). Consider setting up the DEFAULT cache under high request load, too.

* Run more Stator worker containers to handle a higher processing load (Stator
  handles pulling profiles, fanning out messages to followers, and processing
  stats, among others). You'll generally see Stator load climb roughly in
  relation to the sum of the number of followers each user in your instance has;
  a "celebrity" or other popular account will give Stator a lot of work as it
  has to send a copy of each of their posts to every follower, separately.

As you scale up the number of containers, keep the PostgreSQL connection limit
in mind; this is generally the first thing that will fail, as Stator workers in
particular are quite connection-hungry (the parallel nature of their internal
processing means they might be working on 50 different objects at once). It's
generally a good idea to set it as high as your PostgreSQL server will take
(consult PostgreSQL tuning guides for the effect changing that settting has
on memory usage, specifically).

If you end up having a large server that is running into database performance
problems, please get in touch with us and discuss it; Takahē is young enough
that we need data and insight from those installations to help optimise it more.


Federation
----------

ActivityPub, as a federated protocol, involves talking to a lot of other
servers. Sometimes, those servers may be under heavy load and not respond
when Takahē tries to go and fetch user details, posts, or images.

There is a ``TAKAHE_REMOTE_TIMEOUT`` setting to specify the number of seconds
Takahē will wait when making remote requests to other Fediverse instances; it
is set to 5 seconds by default. We recommend you keep this relatively low,
unless for some reason your server is on a very slow internet link.

This may also be a tuple of four floats to set the timeouts for
connect, read, write, and pool timeouts::

  TAKAHE_REMOTE_TIMEOUT='[0.5, 1.0, 1.0, 0.5]'

Note that if your server is unreachable (including being so slow that other
servers' timeouts make the connection fail) for more than about a week, some
servers may consider it permanently unreachable and stop sending posts.


Caching
-------

By default Takakē has caching disabled. The caching needs of a server can
varying drastically based upon the number of users and how interconnected
they are with other servers.

There are multiple ways Takahē uses caches:

* For caching rendered pages and responses, like user profile information.
  These caches reduce database load on your server and improve performance.

* For proxying and caching remote user images and post images. These must be
  proxied to protect your users' privacy; also caching these reduces
  your server's consumed bandwidth and improves users' loading times.

The exact caches you can configure are:

* ``TAKAHE_CACHES_DEFAULT``: Rendered page and response caching

* ``TAKAHE_CACHES_MEDIA``: Remote post images and user profile header pictures

* ``TAKAHE_CACHES_AVATARS``: Remote user avatars ("icons") only

We recommend you set up ``TAKAHE_CACHES_MEDIA`` and ``TAKAHE_CACHES_AVATARS``
at a bare minimum - proxying these all the time without caching will eat into
your server's bandwidth.

All caches are configured the same way - with a custom cache URI/URL. We
support anything that is available as part of
`django-cache-url <https://github.com/epicserve/django-cache-url>`_, but
some cache backends will require additional Python packages not installed
by default with Takahē. More discussion on backend is below.

All items in the cache come with an expiry set - usually one week - but you
can also configure a maximum cache size on dedicated cache datastores like
Memcache. The key names used by the caches do not overlap, so there is
no need to configure different key prefixes for each of Takahē's caches.


Backends
~~~~~~~~

Redis
#####

Examples::

  redis://redis:6379/0
  redis://user:password@redis:6379/0
  rediss://user:password@redis:6379/0

A Redis-protocol server. Use ``redis://`` for unencrypted communication and
``rediss://`` for TLS.

Redis has a large item size limit and is suitable for all caches. We recommend
that you keep the DEFAULT cache separate from the MEDIA and AVATARS caches, and
set the ``maxmemory`` on both to appropriate values (the proxying caches will
need more memory than the DEFAULT cache).



Memcache
########

Examples::

  memcached://memcache:11211?key_prefix=takahe
  memcached://server1:11211,server2:11211

A remote Memcache-protocol server (or set of servers).

Memcached has a 1MB limit per key by default, so this is only suitable for the
DEFAULT cache and not the AVATARS or MEDIA cache.


Filesystem
##########

Examples::

  file:///var/cache/takahe/

A cache on the local disk.

This *will* work with any of the cache backends, but is probably more suitable
for MEDIA and AVATARS.

Note that if you are running Takahē in a cluster, this cache will not be shared
across different machines. This is not quite as bad as it first seems; it just
means you will have more potential uncached requests until all machines have
a cached copy.


Local Memory
############

Examples::

  locmem://default

A local memory cache, inside the Python process. This will consume additional
memory for the process, and should not be used with the MEDIA or AVATARS caches.

