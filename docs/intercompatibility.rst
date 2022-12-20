Intercompatibility
==================

Takahē aims to be compatible with every modern Fediverse server, but the range
of options means that we cannot exhaustively test with everything.

This page tracks what we have tried and know works, what has known issues, and
what we know doesn't work.


Full Support
------------

These servers are our primary testbed and we support them as far as Takahē's
:doc:`own featureset <features>` allows:

* Mastodon 4.0 and higher


Partial Support
---------------

These servers have been tried and appear to initally work, but more testing is
needed:

* Akkoma
* Gotosocial
* Peertube
* Pixelfed
* Pleroma


Known Issues
------------

These servers have the beginnings of support but known bugs that need fixing:

* Mitra
   * Sends Follow Accept messages in a compact format we don't accept yet
