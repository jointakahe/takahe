Domains
=======

One of our key design features in Takahē is that we support multiple different
domains for ActivityPub users to be under.

As a server administrator, you do this by specifying one or more Domains on
your server that users can make Identities (posting accounts) under.

We have two terms for domains:

* **Display Domains** are the domains that appear in handles (for example,
  ``jointakahe.org`` in ``@takahe@jointakahe.org``)

* **Service Domains** are the domains that actually route to Takahē and let
  you access all its pages and APIs.

There's then two ways of running domains given those definitions:

* A domain acting as **both display and service domain**. This is for when
  you're OK giving over a whole domain to Takahē (e.g. ``takahe.social``).

* A separate **display domain** from the **service domain**, for when you still
  want to run a website on the display domain (e.g. ``jointakahe.org``) but
  also want to use it for handles.

Let's look at how to set each type up.


Combined Domain
---------------

In this case, you want to set up a domain that only runs Takahē and doesn't
have any other website to host - an example of this is our own
`takahe.social <https://takahe.social>`_.

To do this, you should set the domain up in Takahē as follows:

* **Domain**: Set this to the domain you're using

* **Service Domain**: Leave this blank (as the one domain is doing both jobs)


Split Domain
------------

In this case, you want to allow users to have handles that include a domain
that is already serving another website - for example, our own
`jointakahe.org <https://jointakahe.org>`_ serves our main webpage, but we also
have our main account as ``@takahe@jointakahe.org``.

To make this work, you need to have a *service domain* - a place where
Takahē (and the *Actor URIs*) for your users live, but which is different to
your main domain you'd like the account handles to contain.

Service domains **must be unique** - they are how we identify what domain the
request that is coming in is for. It doesn't matter what it is, as long as it's
unique and it serves Takahē. For example, ``jointakahe.org`` has a service
domain of ``jointakahe.takahe.social``, but we could also have chosen
``fedi.jointakahe.org`` as long as we served Takahē through there too.

To set this up, you need to:

* Choose a service domain specifically for this display domain and point it at
  Takahē. *You cannot change this domain later without breaking everything*,
  so choose very wisely.

* On your display domain, proxy the URLs ``/.well-known/webfinger``,
  ``/.well-known/nodeinfo`` and ``/.well-known/host-meta`` to your service
  domain (or anything that's serving the same Takahē install).

  .. note::

    You can also do a HTTP redirect rather than proxying if you like, though it
    may be slightly less compatible with all Fediverse server software.

* Set up a domain with:

  * **Domain**: Set this to the display domain
    (the one that doesn't point at Takahē)

  * **Service Domain**: Set this to the service domain (the one that serves
    Takahē)


Example
-------

Let's say that we want to serve three domains from the same Takahē installation:

* ``takahe.social``, which will just serve Takahē directly
* ``jointakahe.org``, which has an existing website that needs to keep working
* ``aeracode.org``, which also has a website that needs to work

We set them up in the following way:

* ``takahe.social``

  * Domain: ``takahe.social``
  * Service Domain: *(left blank)*

* ``jointakahe.org``

  * Domain: ``jointakahe.org``
  * Service Domain: ``jointakahe.takahe.social``

* ``aeracode.org``

  * Domain: ``aeracode.org``
  * Service Domain: ``fedi.aeracode.org``

Then, we need to make sure Takahē is accessible via ``takahe.social``,
``jointakahe.takahe.social`` and ``fedi.aeracode.org``, as these are our
service domains.

Finally, we need to ensure the ``.well-known`` paths are proxied from
``jointakahe.org`` and ``aeracode.org`` to Takahē, as these are the display
domains that have separate service domains.


Technical Details
-----------------

At its core, ActivityPub is a system built around URIs; the
``@username@domain.tld`` format is actually based on Webfinger, a different
standard, and merely used to discover the Actor URI for someone.

Making a system that allows any Webfinger handle to be accepted is relatively
easy, but unfortunately this is only how users are discovered via mentions
and search; when an incoming Follow comes in, or a Post is boosted onto your
timeline, you have to discover the user's Webfinger handle
*from their Actor URI* and this is where it gets tricky.

Mastodon, and from what we can tell most other implementations, do this by
taking the ``preferredUsername`` field from the Actor object, the domain from
the Actor URI, and webfinger that combination of username and domain. This
means that the domain you serve the Actor URI on must uniquely map to a
Webfinger handle domain - they don't need to match, but they do need to be
translatable into one another.

Takahē handles all this internally, however, with a concept of Domains. Each
domain has a primary (display) domain name, and an optional "service" domain;
the primary domain is what we will use for the user's Webfinger handle, and
the service domain is what their Actor URI is served on.

We look at ``HOST`` headers on incoming requests to match users to their
domains, though for Actor URIs we ensure the domain is in the URI anyway.
