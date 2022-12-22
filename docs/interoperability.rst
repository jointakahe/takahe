Interoperability
================

Takahē aims to be compatible with every modern Fediverse server and Mastodon
client app, but the range of options means that we cannot exhaustively test
with everything.

This page tracks what we have tried and know works, what has known issues, and
what we know doesn't work.


Client Apps
-----------

These apps are known to fully work as far as Takahē's
:doc:`own featureset <features>` allows:

* Tusky


These apps have had initial testing and work at a basic level:

* Ivory
* Pinafore


Fediverse Servers
-----------------

These servers are known to fully work as far as Takahē's
:doc:`own featureset <features>` allows:

* Mastodon 4.0 and higher


These servers have been tried and appear to initally work, but more testing is
needed:

* Akkoma

* Peertube

* Pixelfed
   * Replies may not federate?

* Pleroma


These servers have the beginnings of support but known bugs that need fixing:

* Gotosocial
   * Issues pulling accounts

* Mitra
   * Sends Follow Accept messages in a compact format we don't accept yet
