Domains
=======

One of our key design features in Takahē is that we support multiple different
domains for ActivityPub users to be under.

As a server administrator, you do this by specifying one or more Domains on
your server that users can make Identities (posting accounts) under.

Domains can take two forms:

* **Takahē lives on and serves the domain**. In this case, you just set the domain
  to point to Takahē and ensure you have a matching domain record; ignore the
  "service domain" setting.

* **Takahē handles accounts under the domain but does not live on it**. For
  example, you wanted to service the ``@andrew@aeracode.org`` handle, but there
  is already a site on ``aeracode.org``, and Takahē instead must live elsewhere
  (e.g. ``fedi.aeracode.org``).

In this second case, you need to have a *service domain* - a place where
Takahē and the Actor URIs for your users live, but which is different to your
main domain you'd like the account handles to contain.

Service domains **must be unqiue** - they are how we identify what domain the
request that is coming in is for. It doesn't matter what it is, as long as it's
unique and it serves Takahē. For example, ``jointakahe.org`` has a service
domain of ``jointakahe.takahe.social``, but we could also have chosen
``fedi.jointakahe.org`` as long as we served Takahē through there too.

To set this up, you need to:

* Choose a service domain and point it at Takahē. *You cannot change this
  domain later without breaking everything*, so choose very wisely.

* On your primary domain, forward the URLs ``/.well-known/webfinger``,
  ``/.well-known/nodeinfo`` and ``/.well-known/host-meta`` to Takahē.

* Set up a domain with these separate primary and service domains in its
  record.


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
