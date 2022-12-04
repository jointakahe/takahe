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
