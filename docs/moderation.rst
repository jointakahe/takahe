Moderation
==========

As a server admin, you have both identity-level and server-level moderation
options at your disposal.


Identities
----------

Identities, known as Accounts in Mastodon, have their own handle
(like ``@takahe@jointakahe.org``), and are generally what people think of as
"users".

Takahē distinguishes between the two - for us, a User is a set of login
credentials, while an Identity is the public-facing identity people use to
post. A user can have multiple identities, and an identity can be shared
across multiple users (for example, a brand account that five people can
post from).

You can moderate both local and remote identities, but bear in mind that any
moderation actions on *remote identities* are local to your server only;
they will not propagate over to other servers.

Identity moderation actions are available in the "Identities" admin area.


Limiting
~~~~~~~~

Limiting an identity prevents its posts from appearing in the Public and
Federated timelines; they will, however, still appear in the timelines of
people who follow them, be able to notify other people via mentions, and their
replies will appear in conversation threads.

You can limit both local and remote identities. Limiting is reversible,
and encouraged as a way to remove some visibility if you don't want a full block.


Blocking
~~~~~~~~

Blocking an identity erases its existence from your server. Its posts will
not appear anywhere, no mentions from it will come through, and Takahē will
actively discard all incoming information from it as soon as it is received.

If you block a local identity, you are freezing the account and erasing it
from the Fediverse. Takahē will still accept inbound notifications for it,
but if any servers ask if it exists, it will deny its existence. Users trying
to log into that identity will be denied access.

If you block a remote identity, you are almost erasing it from existence
from your server's users. Users will not be able to follow it or see posts
from it; they will, however, be able to mention it in outgoing posts.

Blocking is reversible; however, you will lose data intended for the account
for the duration it is blocked for. If you leave a local account blocked for
too long, other servers will decide it has totally vanished and stop their
users following it.


Servers
-------

If your problem is not with an individual identity/account but with an entire
server - be it very poorly run or actively malicious - you can instead
choose to block the entire server ("defederate").

This is accomplished via the "Federation" admin area. Search and select the
domain you want, and then set it to blocked.

While a domain is blocked, Takahē will actively drop all inbound messages
from it. Blocking is reversible, but you will lose all inbound data from the
server during the blocking period.


Defederating from Takahē
------------------------

Takahē is unusual in the Fediverse in that it's possible to have it claim to be
multiple different domains at once; this extends to the way it speaks to
other servers, and means you cannot easily block an entire Takahē installation at once.

If you wish to block a Takahē server, either from Takahē or any other Fediverse
server that supports defederation, you may choose to either block a single
domain as normal, or you may want to block the entire server.

Takahē sends all actor messages from identities based on the domain they are
part of, but uses a single System Actor for all GET requests to retrieve
identity and post information. To properly defederate a Takahē server, you
need to:

* Block all domains you know it has identities on
* Block the domain of the System Actor (visible at the ``/actor/`` URL)

If you are having trouble blocking a Takahē server due to this, we apologise;
this is the nature of the underlying protocol. If you find a server that breaks
our `Code of Conduct <https://jointakahe.org/conduct/>`_, please let us know
at conduct@jointakahe.org and we will do our best to not give them any support.
