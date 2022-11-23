Stator
======

Takahē's background task system is called Stator, and rather than being a
transitional task queue, it is instead a *reconciliation loop* system; the
workers look for objects that could have actions taken, try to take them, and
update them if successful.

As someone running Takahē, the most important aspects of this are:

* You have to run at least one Stator worker to make things like follows,
  posting, and timelines work.

* You can run as many workers as you want; there is a locking system to ensure
  they can coexist.

* You can get away without running any workers for a few minutes; the server
  will continue to accept posts and follows from other servers, and will
  process them when a worker comes back up.

* There is no separate queue to run, flush or replay; it is all stored in the
  main database.

* If all your workers die, just restart them, and within a few minutes the
  existing locks will time out and the system will recover itself and process
  everything that's pending.

You run a worker via the command ``manage.py runstator``. It will run forever
until it is killed; send SIGINT (Ctrl-C) to it once to have it enter graceful
shutdown, and a second time to force exiting immediately.


Technical Details
-----------------

Each object managed by Stator has a set of extra columns:

* ``state``, the name of a state in a state machine
* ``state_ready``, a boolean saying if it's ready to have a transition tried
* ``state_changed``, when it entered into its current state
* ``state_attempted``, when a transition was last attempted
* ``state_locked_until``, when the entry is locked by a worker until

They also have an associated state machine which is a subclass of
``stator.graph.StateGraph``, which will define a series of states, the
possible transitions between them, and handlers that run for each state to see
if a transition is possible.

An object becoming ready for execution happens first:

* If it's just entered into a new state, or just created, it is marked ready.
* If ``state_attempted`` is far enough in the past (based on the ``try_interval``
  of the current state), a small scheduling loop marks it as ready.

Then, in the main fast loop of the worker, it:

* Selects an item with ``state_ready`` that is in a state it can handle (some
  states are "externally progressed" and will not have handlers run)
* Fires up a coroutine for that handler and lets it run
* When that coroutine exits, sees if it returned a new state name and if so,
  transitions the object to that state.
* If that coroutine errors or exits with ``None`` as a return value, it marks
  down the attempt and leaves the object to be rescheduled after its ``try_interval``.
