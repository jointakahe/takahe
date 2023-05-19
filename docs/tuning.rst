Tuning
======

This page contains a collection of tips and settings that can be used to
tune your server based upon its users and the other servers it federates
with.

We recommend that all installations are run behind a CDN, and
have caches configured. See below for more details on each.


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

* Takahe is run with Gunicorn which spawns several
  [workers](https://docs.gunicorn.org/en/stable/settings.html#workers) to
  handle requests. Depending on what environment you are running Takahe on,
  you might want to customize this via the ``GUNICORN_CMD_ARGS`` environment
  variable. For example - ``GUNICORN_CMD_ARGS="--workers 2"`` to set the
  worker count to 2.


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


Stator (Task Processing)
------------------------

Takahē's background task processing system is called Stator, and it uses
asynchronous Python to pack loads of tasks at once time into a single process.

By default, it will try to run up to 100 tasks at once, with a maximum of 40
from any single model (FanOut will usually be the one it's doing most of).
You can tweak these with the ``TAKAHE_STATOR_CONCURRENCY`` and
``TAKAHE_STATOR_CONCURRENCY_PER_MODEL`` environment variables.

The only real limits Stator can hit are CPU and memory usage; if you see your
Stator (worker) containers not using anywhere near all of their CPU or memory,
you can safely increase these numbers.


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

There are two ways Takahē uses caches:

* For caching rendered pages and responses, like user profile information.
  These caches reduce database load on your server and improve performance.

* For proxying and caching remote user images and post images. These must be
  proxied to protect your users' privacy; also caching these reduces
  your server's consumed bandwidth and improves users' loading times.

By default Takakē has Nginx inside its container image configured to perform
read-through HTTP caching for the image and media files, and no cache
configured for page rendering.

Each cache can be adjusted to your needs; let's talk about both.


Page Caching
~~~~~~~~~~~~

This caching helps Takahē avoid database hits by rendering complex pages or
API endpoints only once, and turning it on will reduce your database load.
There is no cache enabled for this by default

To configure it, set the ``TAKAHE_CACHES_DEFAULT`` environment variable.
We support anything that is available as part of
`django-cache-url <https://github.com/epicserve/django-cache-url>`_, but
some cache backends will require additional Python packages not installed
by default with Takahē. More discussion on some major backends is below.


Redis
#####

Examples::

  redis://redis:6379/0
  redis://user:password@redis:6379/0
  rediss://user:password@redis:6379/0

A Redis-protocol server. Use ``redis://`` for unencrypted communication and
``rediss://`` for TLS.



Memcache
########

Examples::

  memcached://memcache:11211?key_prefix=takahe
  memcached://server1:11211,server2:11211

A remote Memcache-protocol server (or set of servers).


Filesystem
##########

Examples::

  file:///var/cache/takahe/

A cache on the local disk. Slower than other options, and only really useful
if you have no other choice.

Note that if you are running Takahē in a cluster, this cache will not be shared
across different machines. This is not quite as bad as it first seems; it just
means you will have more potential uncached requests until all machines have
a cached copy.


Local Memory
############

Examples::

  locmem://default

A local memory cache, inside the Python process. This will consume additional
memory for the process, and should be used with care.


Image and Media Caching
~~~~~~~~~~~~~~~~~~~~~~~

In order to protect your users' privacy and IP addresses, we can't just send
them the remote URLs of user avatars and post images that aren't on your
server; we instead need to proxy them through Takahē in order to obscure who
is requesting them.

Some other ActivityPub servers do this by downloading all media and images as
soon as they see it, and storing it all locally with some sort of clean-up job;
Takahē instead opts for using a read-through cache for this task, which uses
a bit more bandwidth in the long run but which has much easier maintenance and
better failure modes.

Our Docker image comes with this cache built in, as without it you'll be making
Python do a lot of file proxying on every page load (and it's not the best at
that). It's set to 1GB of disk on each container by default, but you can adjust
this by setting the ``TAKAHE_NGINX_CACHE_SIZE`` environment variable to a value
Nginx understands, like ``10g``.

The cache directory is ``/cache/``, and you can mount a different disk into
this path if you'd like to give it faster or more ephemeral storage.

If you have an external CDN or cache, you can also opt to add your own caching
to these URLs; they all begin with ``/proxy/``, and have appropriate
``Cache-Control`` headers set.


CDNs
----

Takahē can be run behind a CDN if you want to offset some of the load from the
webserver containers. Takahē has to proxy all remote user avatars and images in
order to protect the privacy of your users, and has a built-in cache to help
with this (see "Caching" above), but at large scale this might start to get
strained.

If you do run behind a CDN, ensure that your CDN is set to respect
``Cache-Control`` headers from the origin rather than going purely off of file
extensions. Some CDNs go purely off of file
extensions by default, which will not capture all of the proxy views Takahē
uses to show remote images without leaking user information.

If you don't want to use a CDN but still want a performance improvement, a
read-through cache that respects ``Cache-Control``, like Varnish, will
also help if placed in front of Takahē.


Sentry.io integration
---------------------

Takahē can optionally integrate with https://sentry.io for collection of raised
exceptions from the webserver or Stator.

To enable this, set the ``TAKAHE_SENTRY_DSN`` environment variable to the value
found in your sentry project:
``https://<org>.sentry.io/settings/projects/<project>/keys/``

Other Sentry configuration can be controlled through environment variables
found in ``takahe/settings.py``. See the
`Sentry python documentation <https://docs.sentry.io/platforms/python/configuration/options/>`_
for details.
